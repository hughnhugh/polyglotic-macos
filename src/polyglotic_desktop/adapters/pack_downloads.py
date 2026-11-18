"""Dictionary packs onto this PC (decision 0122): the folder they're kept
in, and their downloads - one at a time, on a thread of their own, never
on the interface thread.

A download, in steps (`core.lexicon.pack_download.Step`):
1. the list, fetched and checked against its signature (`PackList`);
2. free space for the rest of the file;
3. the gzipped file into `<name>.gz.part` beside the packs, carried on
   from where an earlier try stopped (`signed_feed.fetch_to`'s `Range`),
   paused on a connection Windows calls metered unless the learner said
   go on;
4. the whole download checked against the list's size and SHA-256, then
   unpacked into `<name>.part` (never past the list's size) and that
   checked against its own - a file that fails is deleted;
5. opened as the dictionary the list says (language, meanings, tier and
   version from its own `info`), then renamed to its published name and
   its credits written beside it.

A connection lost, the storage failing or no data for `STALL_SEC` is
tried again by itself (`retry_after`), each try from where the last
stopped. Every step goes to the log as content-free facts - the pack, its
version, bytes, the HTTP status, the try, how long - never an address or
a path, so a problem report shows what happened.
"""

import gzip
import hashlib
import logging
import os
import queue
import shutil
import threading
import time
import urllib.error
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from http import HTTPStatus
from pathlib import Path

from polyglotic_desktop.adapters.pack_list import PackList, PackListNotTrusted
from polyglotic_desktop.adapters.signed_feed import OpenUrl, fetch_to
from polyglotic_desktop.adapters.sqlite_dictionary import (
    DictionaryDamaged,
    DictionaryFormatError,
    SqliteDictionary,
)
from polyglotic_desktop.core.lexicon.pack_download import (
    STALL_SEC,
    TRIES,
    PackProgress,
    Problem,
    Rate,
    Step,
    retry_after,
)
from polyglotic_desktop.core.lexicon.packs import (
    RIDER_SUFFIXES,
    BuiltIn,
    FontOffer,
    InstalledPack,
    PackOffer,
    Reader,
    Rider,
    best_offer,
    needs_newer_app,
    newer,
    riders_wanted,
    update_for,
    version_key,
)

log = logging.getLogger(__name__)

ROOM_TO_SPARE = 32_000_000
"""Free space kept beyond a pack's own, so a download never fills the disk."""
REPORT_EVERY_SEC = 0.25
"""At most this often, progress is handed over while bytes arrive."""
METERED_EVERY = 16_000_000
"""While downloading, whether the connection is metered is asked again
every this many bytes."""
BLOCK = 256 * 1024


class PackFailed(Exception):
    """A try failed: why (`problem`), and the HTTP status if the storage
    gave one."""

    def __init__(self, problem: Problem, status: int | None = None) -> None:
        super().__init__(problem.value)
        self.problem = problem
        self.status = status


class Cancelled(Exception):
    """The learner cancelled the download."""


def failure_of(error: BaseException) -> str:
    """A failure as the log says it: its class, and an OSError's number -
    never its message, which can name a folder under the user's name."""
    number = getattr(error, "errno", None)
    return type(error).__name__ + (f" (errno {number})" if number else "")


def _sha256(path: Path, on_block: Callable[[int], None]) -> str:
    digest = hashlib.sha256()
    done = 0
    with path.open("rb") as f:
        while block := f.read(1 << 20):
            digest.update(block)
            done += len(block)
            on_block(done)
    return digest.hexdigest()


def _unpack(
    packed: Path, out: Path, limit: int, on_block: Callable[[int], None]
) -> str:
    """`packed` (gzip) unpacked into `out`, never past `limit` + 1 bytes (a
    file that unpacks longer is cut, then refused by its size: no gzip bomb
    fills the disk); the SHA-256 of what was written."""
    digest = hashlib.sha256()
    done = 0
    with gzip.open(packed, "rb") as source, out.open("wb") as target:
        while done <= limit and (block := source.read(min(1 << 20, limit + 1 - done))):
            target.write(block)
            digest.update(block)
            done += len(block)
            on_block(done)
    return digest.hexdigest()


def _pack_of(path: Path) -> InstalledPack | None:
    """The pack in `path`, by its own `info` - None if it isn't a basic
    dictionary this app reads."""
    try:
        file = SqliteDictionary(path)
    except (DictionaryDamaged, DictionaryFormatError, OSError) as e:
        log.warning("dictionary pack left out: %s", type(e).__name__)
        return None
    try:
        info = file.info
    finally:
        file.close()
    language = info.get("language", "")
    if info.get("tier") != "basic" or not language:
        return None
    return InstalledPack(
        language=language,
        meanings=info.get("meanings_language", "en") or "en",
        dictionary=info.get("dictionary", ""),
        version=info.get("pack_version", "0") or "0",
        file=path.name,
        size=path.stat().st_size,
    )


class PackFolder:
    """The packs on this PC: one folder (`main.packs_folder`, decision
    0089), each file read by its own `info` - no second record to drift
    from it. `also`: folders read too, never written (the installer's own
    packs, decision 0124)."""

    def __init__(self, folder: Path, also: Iterable[Path] = ()) -> None:
        self.folder = folder
        self.also = tuple(also)

    def installed(self) -> dict[tuple[str, str], tuple[InstalledPack, Path]]:
        """The newest pack per language and meanings language."""
        found: dict[tuple[str, str], tuple[InstalledPack, Path]] = {}
        for folder in (self.folder, *self.also):
            for path in sorted(folder.glob("*.sqlite")) if folder.is_dir() else ():
                pack = _pack_of(path)
                if pack is None:
                    continue
                key = (pack.language, pack.meanings)
                held = found.get(key)
                if held is None or (version_key(pack.version) or ()) > (
                    version_key(held[0].version) or ()
                ):
                    found[key] = (pack, path)
        return found

    def outdated(self) -> list[Path]:
        """Files in the folder (never `also`) an `installed` one of the same
        language and meanings supersedes: left by an update that couldn't
        delete them while they were open."""
        newest = {path for _, path in self.installed().values()}
        old = []
        for path in (
            sorted(self.folder.glob("*.sqlite")) if self.folder.is_dir() else ()
        ):
            pack = _pack_of(path) if path not in newest else None
            if pack is not None and (pack.language, pack.meanings) in self.installed():
                old.append(path)
        return old

    def remove(self, paths: Iterable[Path]) -> int:
        """Deletes `paths` (in the folder, never `also`); the bytes freed. A
        file Windows won't let go of yet stays, and goes at a later start
        (`outdated`)."""
        freed = 0
        for path in paths:
            if path.parent != self.folder:
                continue
            try:
                size = path.stat().st_size
                path.unlink()
            except OSError as e:
                log.info("dictionary pack kept for now (%s)", type(e).__name__)
                continue
            freed += size
        return freed

    def riders(self, dictionary: str) -> list[Path]:
        """`dictionary`'s rider files in the folder (never `also`): its
        recordings and its meanings files, of any version."""
        if not self.folder.is_dir():
            return []
        return sorted(
            path
            for suffixes in RIDER_SUFFIXES.values()
            for suffix in suffixes
            for path in self.folder.glob(f"{dictionary}-*{suffix}")
        )

    def outdated_riders(self) -> list[Path]:
        """Rider files in the folder a newer version of the same file
        supersedes (`<dictionary>[-<language>]-<version>.<kind>`): left when
        a pack's update brought new ones."""
        newest: dict[tuple[str, str], tuple[tuple[int, ...], Path]] = {}
        every: list[tuple[tuple[str, str], Path]] = []
        for suffix in (s for suffixes in RIDER_SUFFIXES.values() for s in suffixes):
            for path in (
                sorted(self.folder.glob(f"*{suffix}")) if self.folder.is_dir() else ()
            ):
                name, _, version = path.name[: -len(suffix)].rpartition("-")
                key, order = (name, suffix), version_key(version) or ()
                every.append((key, path))
                if key not in newest or order > newest[key][0]:
                    newest[key] = (order, path)
        return [path for key, path in every if newest[key][1] != path]

    def part(self, offer: PackOffer | Rider) -> Path:
        """Where `offer`'s download comes down, gzipped, until it's whole."""
        return self.folder / (offer.download + ".part")

    def unpacking(self, offer: PackOffer | Rider) -> Path:
        """Where it's unpacked to, until it's checked and opened."""
        return self.folder / (offer.file + ".part")

    def drop_parts(self, offer: PackOffer) -> None:
        """Other versions' downloads cut short, of `offer`'s pack: never to be
        carried on from (and any unpacking left by an end mid-way)."""
        prefix = f"{offer.dictionary}-{offer.meanings}-"
        for part in self.folder.glob(prefix + "*.part"):
            if part != self.part(offer):
                part.unlink(missing_ok=True)


@dataclass(frozen=True)
class Wanted:
    """A download asked for."""

    language: str
    meanings: str
    metered_ok: bool = False
    """The learner said go on, on a metered connection."""
    update: bool = False
    built_in: str = ""
    """A dictionary built into the app (`cedict`): its riders, not a pack
    (decision 0197) - always quietly, as an update is."""
    font: str = ""
    """A caption face (`notosanstc`): its riders, not a pack (polyglotic-hq
    482) - each step said, as a pack's are."""


class PackDeliveries:
    """Downloads packs one at a time on a thread of its own, reporting each
    step (`on_progress`, from that thread) and handing each installed pack
    over (`on_installed`, from that thread too: the caller moves both to
    its own). `metered`: whether Windows calls the connection metered.
    `on_listed`: a refresh's list - the one kept if it couldn't be read -
    and why it couldn't (None: read now)."""

    def __init__(
        self,
        packs: PackList,
        folder: PackFolder,
        reader: Reader,
        on_progress: Callable[[PackProgress], None],
        on_installed: Callable[[PackOffer, Path], None],
        on_listed: Callable[
            [tuple[PackOffer, ...] | None, Problem | None], None
        ] = lambda _o, _p: None,
        on_rider: Callable[
            [PackOffer | BuiltIn | FontOffer, Rider, Path], None
        ] = lambda _o, _r, _p: None,
        metered: Callable[[], bool] = lambda: False,
        open_url: OpenUrl | None = None,
        clock: Callable[[], float] = time.monotonic,
        free_space: Callable[[Path], int] = lambda p: shutil.disk_usage(p).free,
        stall_sec: float = STALL_SEC,
        retry: Callable[[int, Problem], float | None] = retry_after,
        explained_in: str | None = None,
    ) -> None:
        """`explained_in`: the learner's language, whose meanings riders
        come with a pack (decision 0234; None: none)."""
        self._packs = packs
        self.folder = folder
        self.reader = reader
        self.explained_in = explained_in
        self._progress = on_progress
        self._installed = on_installed
        self._listed = on_listed
        self._rider = on_rider
        self._metered = metered
        self._open_url = open_url
        self._clock = clock
        self._free = free_space
        self._stall = stall_sec
        self._retry = retry
        self._queue: queue.Queue[Wanted | str | None] = queue.Queue()
        self._lock = threading.Lock()
        self._cancelled: set[str] = set()
        self._now = threading.Event()  # a wait for the next try cut short
        self._current: str | None = None
        self._waiting: list[str] = []
        self._go_on = False  # Download anyway, for the current download
        self._pausing = False  # the current download waits: for a try, or a go on
        self._last: dict[str, PackProgress] = {}  # each language's, as said last
        self._parts: dict[str, Path] = {}  # each language's download, once known
        self._reported = 0.0
        self.offers: tuple[PackOffer, ...] | None = packs.kept()
        """The list as last checked (None: never): read on the worker
        thread; on any other, a snapshot."""
        self._thread = threading.Thread(
            target=self._work, name="dictionary packs", daemon=True
        )
        self._thread.start()

    @property
    def fonts(self) -> tuple[FontOffer, ...]:
        """The caption faces the list last read offers (polyglotic-hq 482)."""
        return self._packs.fonts

    # -- asked from any thread ------------------------------------------------

    def refresh(self) -> None:
        """Fetch and check the list again, then `on_listed`."""
        self._queue.put("list")

    def want(
        self,
        language: str,
        meanings: str,
        metered_ok: bool = False,
        update: bool = False,
        built_in: str = "",
        font: str = "",
    ) -> None:
        """`language`'s pack in `meanings`; with `built_in` (a dictionary's
        name), that built-in dictionary's riders instead, quietly; with
        `font` (a caption face's name), its files, `language` naming the
        download (`font_download`)."""
        update = update or bool(built_in)
        with self._lock:
            self._cancelled.discard(language)
            if language == self._current:  # under way: Retry now, Download anyway
                if self._pausing:
                    self._go_on = metered_ok or self._go_on
                    self._now.set()
                return
            if language in self._waiting:
                return
            ahead = self._current is not None or any(
                other not in self._cancelled for other in self._waiting
            )
            self._waiting.append(language)
        if not update:
            # waiting only behind another download; else the list comes first
            # (329's QA: "Waiting for another dictionary" with none ahead)
            step = Step.WAITING if ahead else Step.LIST
            self._progress(PackProgress(language, step))
        self._queue.put(Wanted(language, meanings, metered_ok, update, built_in, font))

    def cancel(self, language: str) -> None:
        """Stops it, and deletes what was downloaded."""
        with self._lock:
            self._cancelled.add(language)
            if language == self._current and self._pausing:
                self._now.set()

    def close(self) -> None:
        self._queue.put(None)

    def join(self, timeout: float) -> None:
        self._thread.join(timeout)

    # -- the worker -----------------------------------------------------------

    def _work(self) -> None:
        while (task := self._queue.get()) is not None:
            if task == "list":
                self._refresh()
                continue
            assert isinstance(task, Wanted)
            with self._lock:
                if task.language in self._waiting:
                    self._waiting.remove(task.language)
                if task.language in self._cancelled:
                    self._progress(PackProgress(task.language, Step.CANCELLED))
                    continue
                self._current = task.language
                self._go_on = task.metered_ok
                self._now.clear()
            final = None
            try:
                final = self._deliver(task)
            except Exception as e:  # noqa: BLE001 - never the thread's end: the next runs
                log.error("dictionary pack: unexpected failure: %s", failure_of(e))
            finally:
                with self._lock:
                    self._current = None
            if final is not None:  # said once it's over: a Retry then starts anew
                self._progress(final)

    def _cancelled_now(self, language: str) -> bool:
        with self._lock:
            return language in self._cancelled

    def _refresh(self) -> None:
        """The list read again for Learning - whatever goes wrong, said in
        the log and handed over as the list kept (None if there's none) with
        why it wasn't read (`on_listed`'s problem: `NOT_OFFERED` for none
        published, a 404 - so Learning says no dictionary is ready rather
        than promise one; polyglotic-hq 330), and asked again the next time
        Learning wants it: a refresh never ends this thread (a list refused,
        missing, or a failure of any kind)."""
        problem: Problem | None = None
        try:
            offers: tuple[PackOffer, ...] | None = self._list()
        except PackFailed as failed:
            offers, problem = self.offers, failed.problem
        except Exception as e:  # noqa: BLE001 - a refresh never ends the thread
            log.error("packs list: unexpected failure: %s", failure_of(e))
            offers, problem = self.offers, Problem.OFFLINE
        self._listed(offers, problem)

    def _list(self) -> tuple[PackOffer, ...]:
        """The list fetched and checked; a failure is a `PackFailed`. None
        published (404) is `NOT_OFFERED` - "not ready yet", calmly: the state
        before the first upload, and for an old app after a new list format."""
        started = self._clock()
        try:
            offers = self._packs.fetch()
        except PackListNotTrusted as e:
            log.warning("packs list refused: %s", e)
            raise PackFailed(Problem.LIST_REFUSED) from None
        except urllib.error.HTTPError as e:
            log.info("packs list not fetched: HTTP %d", e.code)
            if e.code == HTTPStatus.NOT_FOUND:
                raise PackFailed(Problem.NOT_OFFERED) from None
            raise PackFailed(Problem.SERVER, e.code) from None
        except (OSError, ValueError) as e:  # URLError, timeouts, a refused TLS
            log.info("packs list not fetched: %s", type(e).__name__)
            raise PackFailed(Problem.OFFLINE) from None
        self.offers = offers
        log.info(
            "packs list checked: %d packs (%.0f ms)",
            len(offers),
            1000 * (self._clock() - started),
        )
        return offers

    def _deliver(self, wanted: Wanted) -> PackProgress | None:
        """Tries until it's installed, cancelled, or stopped; what to say
        once it's over (None: said already, or quiet)."""
        language, tries = wanted.language, 0
        progress = PackProgress(language, Step.LIST, update=wanted.update)
        while True:
            tries += 1
            progress = replace(progress, tries=tries, problem=None, retry_in=None)
            try:
                self._try(wanted, progress)
                return None
            except Cancelled:
                return self._dropped(language)
            except PackFailed as failed:
                wait = self._retry(tries, failed.problem)
                log.info(
                    "dictionary pack %s: try %d of %d failed: %s%s%s",
                    language,
                    tries,
                    TRIES,
                    failed.problem.value,
                    f" (HTTP {failed.status})" if failed.status else "",
                    f"; next try in {wait:.0f} s" if wait is not None else "",
                )
                progress = replace(
                    self._last.get(language, progress),
                    problem=failed.problem,
                    status=failed.status,
                    tries=tries,
                    retry_in=wait,
                    seconds_left=None,
                )
                if wanted.update and failed.problem is not Problem.NO_ROOM:
                    return None  # quiet: tried again at the next day's check
                if failed.problem is Problem.METERED:
                    self._pause()  # before it's said: a click then is heard
                    self._progress(progress)
                    if not self._wait_for_go_on():
                        return self._dropped(language)
                    wanted = replace(wanted, metered_ok=True)
                    tries = 0
                    continue
                if wait is None:
                    return progress
                self._pause()
                self._progress(progress)
                if not self._wait(wait, progress):
                    return self._dropped(language)

    def _pause(self) -> None:
        """The current download waits from now: a Retry or Download anyway
        asked from here on cuts the wait short (`want`)."""
        with self._lock:
            self._pausing = True

    def _dropped(self, language: str) -> PackProgress:
        """Cancelled: what was downloaded is deleted."""
        part = self._parts.pop(language, None)
        if part is not None:
            part.unlink(missing_ok=True)
        log.info("dictionary pack %s: cancelled", language)
        return PackProgress(language, Step.CANCELLED)

    def _wait(self, seconds: float, progress: PackProgress) -> bool:
        """Waits for the next try - counting down, each second said - or
        until Retry cuts it short; False if cancelled meanwhile."""
        end = self._clock() + seconds
        while (left := end - self._clock()) > 0:
            if self._now.wait(min(1.0, left)):
                break
            self._progress(replace(progress, retry_in=max(0.0, end - self._clock())))
        return self._resumed(progress.language)

    def _wait_for_go_on(self) -> bool:
        """Paused on a metered connection until the learner says go on (or
        cancels), or Windows stops calling it metered; False if cancelled."""
        with self._lock:
            language = self._current or ""
        while not self._now.wait(5.0):
            if not self._metered():
                break
        return self._resumed(language)

    def _resumed(self, language: str) -> bool:
        with self._lock:
            self._pausing = False
            self._now.clear()
            return language not in self._cancelled

    def _try(self, wanted: Wanted, progress: PackProgress) -> None:
        if wanted.font:
            self._font(wanted, progress)
            return
        if wanted.built_in:  # no pack: the list's entry for it (decision 0197)
            self._list()
            for entry in self._packs.built_in:
                if entry.dictionary == wanted.built_in:
                    self._riders(wanted, entry, progress)
            return
        language = wanted.language
        started = self._clock()
        self._report(progress, force=True)
        offers = self._list()
        offer = best_offer(offers, language, wanted.meanings, self.reader)
        if offer is None:
            newer_app = needs_newer_app(offers, language, wanted.meanings, self.reader)
            raise PackFailed(
                Problem.NEEDS_NEWER_APP if newer_app else Problem.NOT_OFFERED
            )
        installed = self.folder.installed().get((offer.language, offer.meanings))
        if wanted.update and (
            installed is None or update_for(installed[0], offers, self.reader) is None
        ):
            if installed is not None and installed[0].version == offer.version:
                self._riders(wanted, offer, progress)  # one that didn't arrive
            return  # nothing newer after all
        here = installed[0].version if installed is not None else None
        if installed is not None and installed[0].version == offer.version:
            log.info(
                "dictionary pack %s %s: on this PC already", language, offer.version
            )
            self._progress(
                PackProgress(language, Step.DONE, offer.gz_size, offer.gz_size)
            )
            self._installed(offer, installed[1])
            self._riders(wanted, offer, progress)
            return
        if here is not None and not newer(offer.version, here):
            # never an older version over a newer one, whatever a list says
            log.info(
                "dictionary pack %s: %s on this PC is newer than the list's %s",
                language,
                here,
                offer.version,
            )
            self._progress(PackProgress(language, Step.DONE))
            return
        self.folder.folder.mkdir(parents=True, exist_ok=True)
        self.folder.drop_parts(offer)
        part = self.folder.part(offer)
        self._parts[language] = part
        have = part.stat().st_size if part.is_file() else 0
        needed = offer.gz_size - have + offer.size + ROOM_TO_SPARE  # both, a while
        if self._free(self.folder.folder) < needed:
            self._last[language] = replace(progress, needed=needed - ROOM_TO_SPARE)
            raise PackFailed(Problem.NO_ROOM)
        if not wanted.metered_ok and not self._go_on and self._metered():
            self._last[language] = replace(
                progress, step=Step.DOWNLOADING, done=have, total=offer.gz_size
            )
            raise PackFailed(Problem.METERED)
        self._download(
            wanted, offer, part, have, replace(progress, total=offer.gz_size)
        )
        path = self._check_and_open(offer, part, progress)
        log.info(
            "dictionary pack %s/%s %s: installed, %d bytes, try %d (%.1f s)",
            offer.language,
            offer.meanings,
            offer.version,
            offer.size,
            progress.tries,
            self._clock() - started,
        )
        self._progress(
            PackProgress(
                language, Step.DONE, offer.gz_size, offer.gz_size, update=wanted.update
            )
        )
        self._installed(offer, path)
        self._riders(wanted, offer, progress)

    def _riders(
        self, wanted: Wanted, offer: PackOffer | BuiltIn, progress: PackProgress
    ) -> None:
        """The pack's (or a built-in dictionary's) riders this app wants and
        hasn't got (decision 0133),
        each downloaded and checked as the pack was, quietly: the pack is in
        use already, so nothing is said, and one that fails is tried again
        with the next day's check (or the next time its pack is asked for).
        On a metered connection none is fetched unless the learner said go on."""
        quiet = replace(progress, update=True)
        for rider in riders_wanted(offer, self.reader, self.explained_in):
            path = self.folder.folder / rider.file
            if path.is_file() and path.stat().st_size == rider.size:
                continue
            try:
                if not wanted.metered_ok and not self._go_on and self._metered():
                    raise PackFailed(Problem.METERED)
                # a built-in dictionary's may be the first file in it
                self.folder.folder.mkdir(parents=True, exist_ok=True)
                part = self.folder.part(rider)
                have = part.stat().st_size if part.is_file() else 0
                if self._free(self.folder.folder) < rider.gz_size + rider.size:
                    raise PackFailed(Problem.NO_ROOM)
                self._download(wanted, rider, part, have, quiet)
                unpacked = self._checked(rider, part, quiet, offer.language)
                os.replace(unpacked, path)
            except Cancelled:
                return
            except PackFailed as failed:
                log.info(
                    "dictionary pack %s: its %s file not fetched: %s",
                    offer.language,
                    rider.kind,
                    failed.problem.value,
                )
                continue
            log.info(
                "dictionary pack %s: its %s file is in (%d bytes)",
                offer.language,
                rider.kind,
                rider.size,
            )
            self._rider(offer, rider, path)

    def _font(self, wanted: Wanted, progress: PackProgress) -> None:
        """A caption face's files (its riders) this app reads and hasn't
        got, downloaded and checked as a pack's are, one after another, each
        step said as one download's (polyglotic-hq 482); then done."""
        self._report(progress, force=True)
        self._list()
        offer = next((f for f in self._packs.fonts if f.font == wanted.font), None)
        if offer is None:
            raise PackFailed(Problem.NOT_OFFERED)
        riders = riders_wanted(offer, self.reader)
        if not riders:
            raise PackFailed(Problem.NEEDS_NEWER_APP)
        language, total = wanted.language, sum(r.gz_size for r in riders)
        progress = replace(progress, total=total)
        done = 0
        self.folder.folder.mkdir(parents=True, exist_ok=True)
        for rider in riders:
            path = self.folder.folder / rider.file
            if not (path.is_file() and path.stat().st_size == rider.size):
                if not wanted.metered_ok and not self._go_on and self._metered():
                    self._last[language] = replace(
                        progress, step=Step.DOWNLOADING, done=done
                    )
                    raise PackFailed(Problem.METERED)
                part = self.folder.part(rider)
                self._parts[language] = part
                have = part.stat().st_size if part.is_file() else 0
                if self._free(self.folder.folder) < rider.gz_size + rider.size:
                    self._last[language] = replace(
                        progress, needed=rider.gz_size + rider.size
                    )
                    raise PackFailed(Problem.NO_ROOM)
                self._download(wanted, rider, part, have, progress, offset=done)
                unpacked = self._checked(rider, part, progress, language)
                os.replace(unpacked, path)
                log.info("caption face %s: %s is in", offer.font, rider.file)
                self._rider(offer, rider, path)
            done += rider.gz_size
        self._progress(
            PackProgress(language, Step.DONE, total, total, update=wanted.update)
        )

    def _download(
        self,
        wanted: Wanted,
        offer: PackOffer | Rider,
        part: Path,
        have: int,
        progress: PackProgress,
        offset: int = 0,
    ) -> None:
        """`offer`'s file into `part` from byte `have`; said as `progress`,
        `offset` bytes of it done before this file (a caption face's
        files are one download)."""
        language = wanted.language
        rate = Rate()
        started = self._clock()
        next_metered = have + METERED_EVERY
        log.info(
            "dictionary pack %s: %s: downloading from byte %d of %d, try %d",
            language,
            offer.file,
            have,
            offer.gz_size,
            progress.tries,
        )
        state = replace(progress, step=Step.DOWNLOADING, done=offset + have)
        total = (
            progress.total
            if offset or progress.total > offer.gz_size
            else offer.gz_size
        )
        self._report(state, force=True)

        def on_block(done: int) -> bool:
            nonlocal state, next_metered
            if self._cancelled_now(language):
                return False
            now = self._clock()
            rate.add(now, done)
            state = replace(
                state,
                done=offset + done,
                seconds_left=rate.seconds_left(total - offset),
            )
            self._report(state)
            if done >= next_metered:
                next_metered = done + METERED_EVERY
                if not wanted.metered_ok and not self._go_on and self._metered():
                    return False
            return True

        try:
            if have < offer.gz_size:
                fetch_to(
                    self._packs.file_address(offer),
                    part,
                    offer.gz_size + 1,  # one more: a longer file is cut and refused
                    open_url=self._open_url,
                    timeout=self._stall,
                    on_block=on_block,
                    block=BLOCK,
                )
        except urllib.error.HTTPError as e:
            if e.code == HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE:
                part.unlink(missing_ok=True)  # not ours to carry on: anew
            raise PackFailed(Problem.SERVER, e.code) from None
        except TimeoutError:
            self._last[language] = state
            raise PackFailed(Problem.STALLED) from None
        except (OSError, ValueError) as e:
            log.info("dictionary pack %s: connection: %s", language, type(e).__name__)
            self._last[language] = state
            raise PackFailed(Problem.OFFLINE) from None
        self._last[language] = state
        if self._cancelled_now(language):
            raise Cancelled
        got = part.stat().st_size if part.is_file() else 0
        log.info(
            "dictionary pack %s: %d bytes this try (%.1f s)",
            language,
            got - have,
            self._clock() - started,
        )
        if got < offer.gz_size:
            if not wanted.metered_ok and not self._go_on and self._metered():
                raise PackFailed(Problem.METERED)
            raise PackFailed(Problem.OFFLINE)  # the connection ended early

    def _check_and_open(
        self, offer: PackOffer, part: Path, progress: PackProgress
    ) -> Path:
        """The download checked whole, unpacked, the unpacked file checked,
        opened as the pack the list says, then put in place."""
        language = offer.language
        part = self._checked(offer, part, progress, language)
        self._report(
            replace(progress, step=Step.OPENING, done=offer.size, total=offer.size),
            force=True,
        )
        pack = _pack_of(part)
        if pack is None or (pack.language, pack.meanings, pack.version) != (
            offer.language,
            offer.meanings,
            offer.version,
        ):
            part.unlink(missing_ok=True)
            log.warning(
                "dictionary pack %s: not the pack the list says: deleted", language
            )
            raise PackFailed(Problem.UNREADABLE)
        path = self.folder.folder / offer.file
        os.replace(part, path)
        if offer.credits_text:
            credits = self.folder.folder / f"{offer.dictionary}.CREDITS.md"
            credits.write_text(offer.credits_text, encoding="utf-8")
        return path

    def _checked(
        self,
        offer: PackOffer | Rider,
        part: Path,
        progress: PackProgress,
        language: str,
    ) -> Path:
        """A download (a pack's, or a rider's) checked whole against the
        list, unpacked, and the unpacked file checked: where it is, still
        under its unpacking name. Anything else is deleted and refused."""
        started = self._clock()
        if part.stat().st_size != offer.gz_size:
            part.unlink(missing_ok=True)
            log.warning("dictionary pack %s: not the list's size: deleted", language)
            raise PackFailed(Problem.FILE_REFUSED)
        checking = replace(progress, step=Step.CHECKING, done=0, total=offer.gz_size)
        self._report(checking, force=True)
        digest = _sha256(part, lambda done: self._report(replace(checking, done=done)))
        if digest != offer.gz_sha256:
            part.unlink(missing_ok=True)
            log.warning("dictionary pack %s: not the list's SHA-256: deleted", language)
            raise PackFailed(Problem.FILE_REFUSED)
        unpacked = self.folder.unpacking(offer)
        checking = replace(checking, done=0, total=offer.size)
        try:
            digest = _unpack(
                part,
                unpacked,
                offer.size,
                lambda done: self._report(replace(checking, done=done)),
            )
        except (OSError, EOFError, zlib.error) as e:  # BadGzipFile is an OSError
            unpacked.unlink(missing_ok=True)
            part.unlink(missing_ok=True)
            log.warning(
                "dictionary pack %s: not unpacked: %s", language, type(e).__name__
            )
            raise PackFailed(Problem.FILE_REFUSED) from None
        part.unlink(missing_ok=True)
        if unpacked.stat().st_size != offer.size or digest != offer.sha256:
            unpacked.unlink(missing_ok=True)
            log.warning(
                "dictionary pack %s: unpacked, not the list's: deleted", language
            )
            raise PackFailed(Problem.FILE_REFUSED)
        log.info(
            "dictionary pack %s: checked and unpacked (%.1f s)",
            language,
            self._clock() - started,
        )
        return unpacked

    def _report(self, progress: PackProgress, force: bool = False) -> None:
        """Hands progress over - at most every `REPORT_EVERY_SEC` while bytes
        arrive; a step's start always."""
        now = self._clock()
        if force or now - self._reported >= REPORT_EVERY_SEC:
            self._reported = now
            self._last[progress.language] = progress
            if not progress.update:
                self._progress(progress)
