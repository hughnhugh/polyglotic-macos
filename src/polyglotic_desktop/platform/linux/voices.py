"""Linux's system voice: speech-dispatcher, talked to over its own socket
(polyglotic-hq 546's slice 5, 591; DECISIONS #243 item 3: the recordings,
then the system's basic voice; decision 0294).

speech-dispatcher is the desktops' speech server - Ubuntu 24.04's desktop
installs it with its espeak-ng voices (the release's manifest, read
2026-11-21), and Orca speaks through it. The app speaks its protocol
(SSIP: lines of text on a Unix socket, `$XDG_RUNTIME_DIR/speech-dispatcher/
speechd.sock`) with nothing of its own installed: no library of
speech-dispatcher's or espeak-ng's is loaded into the app.

- **Starting it:** a desktop with systemd starts it when its socket is
  first used; elsewhere, no socket, the app starts it as speech-dispatcher's
  own library does (`speech-dispatcher --spawn`). Not installed, or not
  starting: an `OSError` that says which (`NOT_INSTALLED`), and the
  speaker goes on with the recordings alone (`RecordedVoices`).
- **Which voices:** each output module's (`LIST OUTPUT_MODULES`), the
  system's default module first; of espeak-ng's 13,362 listed on Ubuntu
  24.04 only the 131 plain ones (`+Adam`, `+Alex`... are variants of
  them). Their languages as the app's tags (`cmn` is Mandarin, `zh-CN`;
  `yue` Cantonese, `zh-HK`). All `Quality.BASIC`: the word card says so
  each time (518's notice, worded for Linux).
- **Saying a word:** speech-dispatcher makes the sound and plays it - the
  app never has it - so a word is a `DispatcherSays` (`speaking.
  SaysItself`): sent (`SPEAK`), heard to its end when speech-dispatcher
  says `END`, stopped with `CANCEL`. Measured on GitHub's Ubuntu 24.04
  runner (591's probe): the sound began within 20 ms of being sent; a
  cancel stopped it within 20 ms.

Everything here runs on the speaker's thread. Never logs a word said.
"""

import contextlib
import os
import select
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from pathlib import Path

from polyglotic_desktop.platform.linux.system import outside_environment
from polyglotic_desktop.ports.speaker import Quality, Voice

SOCKET = Path("speech-dispatcher") / "speechd.sock"
"""speech-dispatcher's socket, under `$XDG_RUNTIME_DIR`."""
NOT_INSTALLED = "speech-dispatcher isn't installed"
ANSWER_SEC = 5.0
"""An answer not in by then: the connection is given up."""
SPAWN_SEC = 5.0
"""speech-dispatcher started by the app has this long to open its socket
(0.15 s on GitHub's Ubuntu runner)."""
RETRY_SEC = 30.0
"""After it couldn't be reached, it isn't tried again for this long: the
voices are asked about every few seconds while a card is open."""
VOICE = "speechd:"
"""How a voice's id starts here: then its module and its name."""
LANGUAGES = {"cmn": "zh-CN", "yue": "zh-HK", "es": "es-ES", "pt": "pt-PT"}
"""espeak-ng's languages as the app's tags (`views.speech.REGIONS`): its
Mandarin is "cmn", its Cantonese "yue", and Spain's Spanish and
Portugal's Portuguese have no region."""
LONGEST_SEC = 5.0
LONGEST_PER_CHAR_SEC = 0.25
"""A word is given up after `LONGEST_SEC` and this long a character at its
pace: about four times espeak-ng's pace (591's probe: 42 characters in
2.4 s), so only a speech server that stopped answering is cut short."""


def socket_path(environ: Mapping[str, str] | None = None) -> Path:
    """Where speech-dispatcher listens: `$SPEECHD_ADDRESS` if it names a
    Unix socket ("unix_socket:/path"), else `$XDG_RUNTIME_DIR`'s - or, in a
    session without one, the cache folder's, as its own library looks."""
    env = os.environ if environ is None else environ
    method, _, where = env.get("SPEECHD_ADDRESS", "").partition(":")
    if method == "unix_socket" and where:
        return Path(where)
    runtime = env.get("XDG_RUNTIME_DIR", "")
    if runtime and Path(runtime).is_absolute():
        return Path(runtime) / SOCKET
    cache = env.get("XDG_CACHE_HOME", "") or str(Path.home() / ".cache")
    return Path(cache) / SOCKET


def ssip_text(text: str) -> bytes:
    """`text` as SSIP's data: its lines on CRLF, a line starting with a dot
    given a second one, and the lone dot that ends it."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    escaped = ["." + line if line.startswith(".") else line for line in lines]
    return ("\r\n".join(escaped) + "\r\n.\r\n").encode("utf-8")


class Ssip:
    """One SSIP connection on a connected socket, used on one thread:
    `command` waits for its answer; the events speech-dispatcher sends in
    between (`700-799`: a message begun, ended, cancelled) are kept, by
    message, for `ended`. OSError when the connection fails or a command
    is refused."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock
        self._buffer = b""
        self._ends: dict[int, str] = {}
        self.closed = False

    def _fill(self, wait: float) -> bool:
        """Reads what has come within `wait` seconds; False: nothing."""
        ready, _, _ = select.select([self._sock], [], [], max(0.0, wait))
        if not ready:
            return False
        try:
            data = self._sock.recv(65536)
        except OSError:
            data = b""
        if not data:
            self.close()
            raise OSError("speech-dispatcher closed the connection")
        self._buffer += data
        return True

    def _whole(self) -> list[str] | None:
        """The first whole answer or event in what has come - its lines, to
        the one with a space after its code - taken out; None if there's
        none yet. Finds the lines in place: a voice list is 13,362 of them."""
        start = 0
        while True:
            end = self._buffer.find(b"\r\n", start)
            if end < 0:
                return None
            if self._buffer[start + 3 : start + 4] == b" ":
                lines = self._buffer[:end].decode("utf-8", "replace").split("\r\n")
                self._buffer = self._buffer[end + 2 :]
                return lines
            start = end + 2

    def _message(self, until: float | None) -> list[str] | None:
        """The next whole answer or event, waited for until `until` (None:
        only what has come already); None if it isn't all in by then."""
        while True:
            found = self._whole()
            if found is not None:
                return found
            wait = 0.0 if until is None else until - time.monotonic()
            if wait < 0 or not self._fill(wait):
                return None

    def _keep(self, event: list[str]) -> None:
        """An event: `7NN-<message>`, `7NN-<client>`, [a mark], `7NN KIND`."""
        kind = event[-1][4:].strip()
        try:
            message = int(event[0][4:])
        except (ValueError, IndexError):
            return
        if kind in ("END", "CANCELED"):
            self._ends[message] = kind

    def command(self, line: str, data: bytes | None = None) -> list[str]:
        """Sends `line` (and `data` after its 230 answer) and waits for the
        answer: its lines, without the codes. OSError if it's refused or
        doesn't come."""
        if self.closed:
            raise OSError("speech-dispatcher's connection is closed")
        try:
            self._sock.sendall(line.encode("utf-8") + b"\r\n")
            answer = self._answer()
            if data is not None and answer[-1].startswith("230"):
                self._sock.sendall(data)
                answer = self._answer()
        except OSError:
            self.close()
            raise
        code = answer[-1][:3]
        if not code.startswith("2"):
            word = line.split(" ")[0]
            raise OSError(f"speech-dispatcher refused {word}: {answer[-1][4:]}")
        return [part[4:] for part in answer]

    def _answer(self) -> list[str]:
        until = time.monotonic() + ANSWER_SEC
        while True:
            message = self._message(until)
            if message is None:
                self.close()
                raise OSError("speech-dispatcher didn't answer")
            if message[-1].startswith("7"):
                self._keep(message)
                continue
            return message

    def ended(self, message: int) -> str | None:
        """How `message` ended - "END" (heard), "CANCELED" - or None while
        it hasn't: reads what has come, without waiting."""
        while message not in self._ends:
            got = self._message(None)
            if got is None:
                return None
            if got[-1].startswith("7"):
                self._keep(got)
        for older in [m for m in self._ends if m < message]:  # stopped ones'
            del self._ends[older]
        return self._ends.pop(message)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            with contextlib.suppress(OSError):
                self._sock.close()


def _unix_socket(path: Path) -> socket.socket:
    if sys.platform == "win32":
        raise OSError("speech-dispatcher is Linux's")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(ANSWER_SEC)
    try:
        sock.connect(str(path))
    except OSError:
        sock.close()
        raise
    return sock


def connect(
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
    run: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    open_socket: Callable[[Path], socket.socket] = _unix_socket,
) -> Ssip:
    """A connection to speech-dispatcher - started first if nothing listens
    on its socket, as its own library does. OSError: `NOT_INSTALLED`, or
    why it wouldn't start."""
    path = socket_path(environ)
    try:
        return Ssip(open_socket(path))
    except OSError:
        pass  # nothing listens there: started below
    program = which("speech-dispatcher")
    if program is None:
        raise OSError(NOT_INSTALLED)
    try:
        done = run(
            [program, "--spawn", "--communication-method", "unix_socket",
             "--socket-path", str(path)],
            capture_output=True, timeout=SPAWN_SEC, check=False,
            env=outside_environment(environ),
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError) as error:
        raise OSError(f"speech-dispatcher wouldn't start: {error}") from None
    if done.returncode != 0:
        raise OSError(f"speech-dispatcher wouldn't start (exit {done.returncode})")
    end = time.monotonic() + SPAWN_SEC
    while True:
        try:
            return Ssip(open_socket(path))
        except OSError as error:
            if time.monotonic() >= end:
                raise OSError(
                    f"speech-dispatcher didn't open its socket: {error}"
                ) from None
            time.sleep(0.05)


def voice_id(module: str, name: str) -> str:
    return f"{VOICE}{module}:{name}"


def listed_voices(module: str, rows: list[str]) -> list[Voice]:
    """A module's `LIST SYNTHESIS_VOICES` (`name<TAB>language<TAB>variant`)
    as voices: the plain ones only, not their variants."""
    found = []
    for row in rows:
        name, _, rest = row.partition("\t")
        language, _, variant = rest.partition("\t")
        if not name or not language or variant not in ("", "none") or "+" in name:
            continue
        tag = LANGUAGES.get(language, language)
        found.append(Voice(voice_id(module, name), name, tag, Quality.BASIC))
    return found


class DispatcherVoices:
    """`speaking.Voices`: speech-dispatcher's voices, over one connection
    kept while the app runs (made again if it fails). Each module's voices
    are listed once a connection; the modules each time they're asked."""

    def __init__(
        self,
        connection: Callable[[], Ssip] = connect,
        client: str = "polyglotic",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._connect = connection
        self._client = client
        self._clock = clock
        self._ssip: Ssip | None = None
        self._failed_at: float | None = None
        self._failure = ""
        self._listed: dict[str, list[Voice]] = {}
        self._set: dict[str, str] = {}
        """What this connection has set now (module, voice, rate)."""

    def _connection(self) -> Ssip:
        if self._ssip is not None and not self._ssip.closed:
            return self._ssip
        now = self._clock()
        if self._failed_at is not None and now - self._failed_at < RETRY_SEC:
            raise OSError(self._failure)
        try:
            ssip = self._connect()
            user = os.environ.get("USER", "user")
            ssip.command(f"SET self CLIENT_NAME {user}:{self._client}:speaker")
            ssip.command("SET self NOTIFICATION all on")
        except OSError as error:
            self._failed_at, self._failure = now, str(error)
            raise
        self._ssip, self._failed_at = ssip, None
        self._listed, self._set = {}, {}
        return ssip

    def _command(self, line: str, data: bytes | None = None) -> list[str]:
        try:
            return self._connection().command(line, data)
        except OSError:
            if self._ssip is not None and self._ssip.closed:
                self._ssip = None
            raise

    def found(self) -> tuple[Voice, ...]:
        modules = self._command("LIST OUTPUT_MODULES")[:-1]
        default = self._command("GET OUTPUT_MODULE")[0]
        ordered = sorted(modules, key=lambda m: m != default)
        voices: list[Voice] = []
        for module in ordered:
            if module not in self._listed:
                self._setting("OUTPUT_MODULE", module)
                rows = self._command("LIST SYNTHESIS_VOICES")[:-1]
                self._listed[module] = listed_voices(module, rows)
            voices.extend(self._listed[module])
        return tuple(voices)

    def _setting(self, what: str, value: str) -> None:
        if self._set.get(what) != value:
            if what == "OUTPUT_MODULE":
                self._set.pop("SYNTHESIS_VOICE", None)  # a module's own voices
            self._command(f"SET self {what} {value}")
            self._set[what] = value

    def synthesize(self, text: str, voice: Voice, rate: float) -> "DispatcherSays":
        module, _, name = voice.id.removeprefix(VOICE).partition(":")
        if not voice.id.startswith(VOICE) or not name:
            raise OSError("not one of speech-dispatcher's voices")
        return DispatcherSays(self, text, module, name, rate)

    def speak(self, text: str, module: str, name: str, rate: float) -> int:
        """Sends `text` to be said; its message's number."""
        self._setting("OUTPUT_MODULE", module)
        self._setting("SYNTHESIS_VOICE", name)
        self._setting("RATE", str(max(-100, min(100, round((rate - 1.0) * 100)))))
        answer = self._command("SPEAK", ssip_text(text))
        try:
            return int(answer[0])
        except (ValueError, IndexError):
            raise OSError("speech-dispatcher queued it without a number") from None

    def ended(self, message: int) -> str | None:
        """How `message` ended (`Ssip.ended`); "FAILED" if the connection did."""
        if self._ssip is None or self._ssip.closed:
            return "FAILED"
        try:
            return self._ssip.ended(message)
        except OSError:
            self._ssip = None
            return "FAILED"

    def cancel(self) -> None:
        with contextlib.suppress(OSError):  # gone: nothing plays
            self._command("CANCEL self")

    def close(self) -> None:
        if self._ssip is not None:
            self._ssip.close()
            self._ssip = None


class DispatcherSays:
    """`speaking.SaysItself`: one chunk said by speech-dispatcher."""

    def __init__(
        self, voices: DispatcherVoices, text: str, module: str, name: str, rate: float
    ) -> None:
        self._voices = voices
        self._text = text
        self._module = module
        self._name = name
        self._rate = rate
        self._message: int | None = None
        self._end: str | None = None
        self.longest = LONGEST_SEC + LONGEST_PER_CHAR_SEC * len(text) / max(rate, 0.25)

    def start(self) -> bool:
        try:
            self._message = self._voices.speak(
                self._text, self._module, self._name, self._rate
            )
        except OSError:
            self._end = "FAILED"
            return False
        return True

    def playing(self) -> bool:
        if self._end is None and self._message is not None:
            self._end = self._voices.ended(self._message)
        return self._end is None and self._message is not None

    @property
    def heard(self) -> bool:
        return self._end == "END"

    def stop(self) -> None:
        if self._message is not None and self._end is None:
            self._voices.cancel()
            self._end = "CANCELED"
