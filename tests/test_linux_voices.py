"""Linux's voice (polyglotic-hq 591, decision 0294): speech-dispatcher talked
to over its socket - its voices listed, a word said, stopped, a connection
lost, speech-dispatcher started where nothing listens, and missing - with
a stand-in speech-dispatcher on a socket pair (`Dispatcher`), on any OS.
The real one, heard at the sound server's monitor, is
`test_linux_voices_heard.py` (GitHub's Ubuntu runner)."""

import contextlib
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from polyglotic_desktop.platform.linux.voices import (
    NOT_INSTALLED,
    RETRY_SEC,
    DispatcherVoices,
    Ssip,
    connect,
    listed_voices,
    socket_path,
    ssip_text,
)
from polyglotic_desktop.platform.recorded_voices import RecordedVoices, Recordings
from polyglotic_desktop.platform.speaking import Clip, SpeakerThread
from polyglotic_desktop.ports.speaker import RECORDED, Quality, Voice

ESPEAK = [
    "Afrikaans\taf\tnone",
    "Afrikaans+Adam\taf\tAdam",
    "Chinese (Mandarin, latin as English)\tcmn\tnone",
    "Chinese (Mandarin, latin as English)+Alex\tcmn\tAlex",
    "Chinese (Cantonese)\tyue\tnone",
    "English (America)\ten-US\tnone",
    "English (America)+Andy\ten-US\tAndy",
    "French (France)\tfr-FR\tnone",
    "Spanish (Spain)\tes\tnone",
]
OPENJTALK = ["Default\tja\tnone"]


class Dispatcher:
    """A stand-in speech-dispatcher on one end of a socket pair: answers
    SSIP as 0.12.0 did on GitHub's Ubuntu 24.04 runner (591's probe); a
    message ends `length` seconds after it begins, unless cancelled."""

    def __init__(self, length: float = 0.2, default: str = "espeak-ng") -> None:
        self.app, self._end = socket.socketpair()
        self.length = length
        self.default = default
        self.commands: list[str] = []
        self.spoken: list[str] = []
        self.module = default
        self._message = 0
        self._ending: threading.Timer | None = None
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _send(self, *lines: str) -> None:
        with self._lock, contextlib.suppress(OSError):
            self._end.sendall("".join(f"{line}\r\n" for line in lines).encode())

    def _event(self, code: int, message: int, kind: str) -> None:
        self._send(f"{code}-{message}", f"{code}-1", f"{code} {kind}")

    def _serve(self) -> None:
        buffer = b""
        reading: list[str] | None = None
        while True:
            try:
                data = self._end.recv(65536)
            except OSError:
                return
            if not data:
                return
            buffer += data
            while b"\r\n" in buffer:
                raw, buffer = buffer.split(b"\r\n", 1)
                line = raw.decode()
                if reading is not None:
                    if line == ".":
                        self._queued("\n".join(reading))
                        reading = None
                    else:
                        reading.append(line)
                    continue
                self.commands.append(line)
                if line == "SPEAK":
                    reading = []
                    self._send("230 OK RECEIVING DATA")
                else:
                    self._answer(line)

    def _queued(self, text: str) -> None:
        self._message += 1
        message = self._message
        self.spoken.append(text)
        self._send(f"225-{message}", "225 OK MESSAGE QUEUED")
        self._event(701, message, "BEGIN")
        self._ending = threading.Timer(self.length, self._event, (702, message, "END"))
        self._ending.start()

    def _answer(self, line: str) -> None:
        if line.startswith("SET self OUTPUT_MODULE "):
            self.module = line.split(" ", 3)[3]
            self._send("216 OK OUTPUT MODULE SET")
        elif line.startswith("SET self "):
            self._send("200 OK SET")
        elif line == "LIST OUTPUT_MODULES":
            self._send("250-espeak-ng", "250-openjtalk", "250 OK MODULE LIST SENT")
        elif line == "GET OUTPUT_MODULE":
            self._send(f"251-{self.default}", "251 OK GET RETURNED")
        elif line == "LIST SYNTHESIS_VOICES":
            rows = ESPEAK if self.module == "espeak-ng" else OPENJTALK
            self._send(*(f"249-{r}" for r in rows), "249 OK VOICE LIST SENT")
        elif line == "CANCEL self":
            if self._ending is not None and self._ending.is_alive():
                self._ending.cancel()
                self._send("213 OK CANCELED")
                self._event(703, self._message, "CANCELED")
            else:
                self._send("213 OK CANCELED")
        else:
            self._send("300 ERR UNKNOWN COMMAND")

    def gone(self) -> None:
        """speech-dispatcher ends: the connection closes."""
        if self._ending is not None:
            self._ending.cancel()
        self._end.close()

    def close(self) -> None:
        self.gone()
        self.app.close()


@pytest.fixture
def dispatcher() -> Iterator[Dispatcher]:
    made = Dispatcher()
    yield made
    made.close()


def voices_over(dispatcher: Dispatcher) -> DispatcherVoices:
    return DispatcherVoices(connection=lambda: Ssip(dispatcher.app))


def wait_until(condition: object, timeout: float = 3.0) -> None:
    give_up = time.monotonic() + timeout
    while not condition():  # type: ignore[operator]
        assert time.monotonic() < give_up, "never happened"
        time.sleep(0.005)


def test_its_voices_are_the_plain_ones_the_systems_module_first(
    dispatcher: Dispatcher,
) -> None:
    voices = voices_over(dispatcher)
    found = voices.found()
    assert [v.name for v in found] == [
        "Afrikaans",
        "Chinese (Mandarin, latin as English)",
        "Chinese (Cantonese)",
        "English (America)",
        "French (France)",
        "Spanish (Spain)",
        "Default",  # openjtalk's Japanese, after the default module's
    ]
    tags = {v.name: v.language for v in found}
    assert tags["Chinese (Mandarin, latin as English)"] == "zh-CN"
    assert tags["Chinese (Cantonese)"] == "zh-HK"
    assert tags["Spanish (Spain)"] == "es-ES" and tags["Default"] == "ja"
    assert {v.quality for v in found} == {Quality.BASIC}  # 518's notice: basic
    assert found[3].id == "speechd:espeak-ng:English (America)"
    # the voices listed once a connection; the modules each time
    assert voices.found() == found
    assert dispatcher.commands.count("LIST SYNTHESIS_VOICES") == 2
    assert dispatcher.commands.count("LIST OUTPUT_MODULES") == 2
    assert dispatcher.commands[:2] == [
        dispatcher.commands[0],
        "SET self NOTIFICATION all on",
    ]
    assert dispatcher.commands[0].startswith("SET self CLIENT_NAME ")
    assert dispatcher.commands[0].endswith(":polyglotic:speaker")


def test_a_word_is_said_in_its_voice_heard_to_its_end(dispatcher: Dispatcher) -> None:
    voices = voices_over(dispatcher)
    french = next(v for v in voices.found() if v.language == "fr-FR")
    says = voices.synthesize("bonjour", french, 1.0)
    assert says.start()
    assert says.playing() and not says.heard
    wait_until(lambda: not says.playing())
    assert says.heard
    said = dispatcher.commands[dispatcher.commands.index("SPEAK") - 3 :]
    assert said[:4] == [
        "SET self OUTPUT_MODULE espeak-ng",
        "SET self SYNTHESIS_VOICE French (France)",
        "SET self RATE 0",
        "SPEAK",
    ]
    assert dispatcher.spoken == ["bonjour"]
    # the same voice again: nothing set again
    again = voices.synthesize("merci", french, 1.0)
    before = len(dispatcher.commands)
    assert again.start()
    assert dispatcher.commands[before:] == ["SPEAK"]
    wait_until(lambda: not again.playing())
    assert again.heard


def test_a_word_stopped_is_cancelled_and_not_heard(dispatcher: Dispatcher) -> None:
    dispatcher.length = 5.0
    voices = voices_over(dispatcher)
    english = next(v for v in voices.found() if v.language == "en-US")
    says = voices.synthesize("a longer sentence", english, 1.0)
    assert says.start() and says.playing()
    says.stop()
    assert "CANCEL self" in dispatcher.commands
    assert not says.playing() and not says.heard
    # the cancelled message's event, arriving after, ends nothing new
    other = voices.synthesize("next", english, 1.0)
    dispatcher.length = 0.05
    assert other.start()
    wait_until(lambda: not other.playing())
    assert other.heard


def test_a_lone_dot_is_kept_and_languages_are_the_apps_tags() -> None:
    assert ssip_text("one\n.\n..two") == b"one\r\n..\r\n...two\r\n.\r\n"
    assert ssip_text("a\r\nb") == b"a\r\nb\r\n.\r\n"
    voices = listed_voices("espeak-ng", ESPEAK)
    assert [v.language for v in voices] == [
        "af",
        "zh-CN",
        "zh-HK",
        "en-US",
        "fr-FR",
        "es-ES",
    ]


def test_rate_is_speech_dispatchers_scale(dispatcher: Dispatcher) -> None:
    voices = voices_over(dispatcher)
    english = next(v for v in voices.found() if v.language == "en-US")
    says = voices.synthesize("slow", english, 0.7)
    assert says.start()
    assert "SET self RATE -30" in dispatcher.commands


def test_a_connection_lost_ends_the_word_and_the_next_ask_connects_again() -> None:
    first, second = Dispatcher(length=5.0), Dispatcher()
    made = iter((first, second))
    connections: list[Dispatcher] = []

    def connection() -> Ssip:
        d = next(made)
        connections.append(d)
        return Ssip(d.app)

    voices = DispatcherVoices(connection=connection)
    try:
        english = next(v for v in voices.found() if v.language == "en-US")
        says = voices.synthesize("hello", english, 1.0)
        assert says.start()
        first.gone()  # speech-dispatcher ended mid-word
        wait_until(lambda: not says.playing())
        assert not says.heard
        assert voices.found()  # made again
        assert len(connections) == 2
    finally:
        first.close()
        second.close()


def test_a_voice_not_its_own_is_refused(dispatcher: Dispatcher) -> None:
    voices = voices_over(dispatcher)
    with pytest.raises(OSError):
        voices.synthesize("x", Voice("zh-1", "Microsoft Huihui", "zh-CN"), 1.0)


def test_the_socket_is_where_its_own_library_looks(tmp_path: Path) -> None:
    run = str(tmp_path / "run")
    assert (
        socket_path({"XDG_RUNTIME_DIR": run})
        == Path(run) / "speech-dispatcher" / "speechd.sock"
    )
    assert socket_path({"SPEECHD_ADDRESS": "unix_socket:/s/sd.sock"}) == Path(
        "/s/sd.sock"
    )
    assert (
        socket_path(
            {"SPEECHD_ADDRESS": "inet_socket:127.0.0.1:6560", "XDG_RUNTIME_DIR": run}
        )
        == Path(run) / "speech-dispatcher" / "speechd.sock"
    )
    cache = str(tmp_path / "cache")
    assert (
        socket_path({"XDG_CACHE_HOME": cache})
        == Path(cache) / "speech-dispatcher" / "speechd.sock"
    )


def test_nothing_listening_starts_it_as_its_own_library_does(tmp_path: Path) -> None:
    started = Dispatcher()
    tries: list[Path] = []
    ran: list[list[str]] = []

    def open_socket(path: Path) -> socket.socket:
        tries.append(path)
        if not ran:
            raise FileNotFoundError(2, "No such file or directory")
        return started.app

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        ran.append(command)
        return subprocess.CompletedProcess(command, 0, b"", b"")

    env = {"XDG_RUNTIME_DIR": str(tmp_path)}
    try:
        made = connect(env, which=lambda _: "/usr/bin/speech-dispatcher", run=run,
                       open_socket=open_socket)  # fmt: skip
        assert ran == [[
            "/usr/bin/speech-dispatcher", "--spawn", "--communication-method",
            "unix_socket", "--socket-path", str(socket_path(env)),
        ]]  # fmt: skip
        assert made.command("LIST OUTPUT_MODULES")[:-1] == ["espeak-ng", "openjtalk"]
        assert len(tries) == 2
    finally:
        started.close()


def test_not_installed_says_so_and_isnt_asked_again_for_a_while() -> None:
    def missing(_path: Path) -> socket.socket:
        raise FileNotFoundError(2, "No such file or directory")

    with pytest.raises(OSError, match=NOT_INSTALLED):
        connect({}, which=lambda _: None, open_socket=missing)
    asked: list[float] = []
    now = [1000.0]

    def connection() -> Ssip:
        asked.append(now[0])
        raise OSError(NOT_INSTALLED)

    voices = DispatcherVoices(connection=connection, clock=lambda: now[0])
    for later in (0.0, 5.0, RETRY_SEC + 1):
        now[0] += later
        with pytest.raises(OSError, match=NOT_INSTALLED):
            voices.found()
    assert len(asked) == 2  # first, then after RETRY_SEC


def test_one_that_wont_start_says_why() -> None:
    def missing(_path: Path) -> socket.socket:
        raise ConnectionRefusedError(111, "Connection refused")

    def refused(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(command, 1, b"", b"autospawn disabled")

    with pytest.raises(OSError, match="wouldn't start"):
        connect({}, which=lambda _: "/usr/bin/speech-dispatcher", run=refused,
                open_socket=missing)  # fmt: skip


PLAYED: list[Clip] = []
"""What `NoOutput` was given to play."""


class NoOutput:
    """`speaking.Output`: plays for the clip's length."""

    def __init__(self) -> None:
        self.until = 0.0

    def start(self, clip: Clip) -> bool:
        PLAYED.append(clip)
        self.until = time.perf_counter() + clip.seconds
        return True

    def playing(self) -> bool:
        return time.perf_counter() < self.until

    def stop(self) -> None:
        pass


class OneWord:
    """A pack's recorded words: "bonjour" only."""

    def clip(self, word: str) -> bytes | None:
        return b"ogg" if word == "bonjour" else None


def test_without_speech_dispatcher_the_recordings_still_play() -> None:
    """The brief's "degrade gracefully": no speech-dispatcher, and a pack's
    recorded word is still said; the rest have no voice."""
    recordings = Recordings()
    recordings.use("fr", "fr-FR", "Kokoro", OneWord())

    def missing() -> Ssip:
        raise OSError(NOT_INSTALLED)

    said = RecordedVoices(
        DispatcherVoices(connection=missing),
        recordings,
        decode=lambda _data: Clip(b"\x10\x27" * 1600, 16_000),
    )
    assert [v.id for v in said.found()] == [f"{RECORDED}fr"]
    PLAYED.clear()
    speaker = SpeakerThread(said, NoOutput)
    ended: list[bool] = []
    done = threading.Event()

    def end(heard: bool) -> None:
        ended.append(heard)
        done.set()

    try:
        speaker.look_for_voices()
        wait_until(lambda: speaker.listed)
        [ours] = speaker.voices()
        speaker.say("bonjour", ours, 1.0, lambda *_: None, end)
        assert done.wait(2) and ended == [True] and len(PLAYED) == 1
        done.clear()
        speaker.say("merci", ours, 1.0, lambda *_: None, end)
        assert done.wait(2) and ended == [True, False]  # not recorded, no voice
    finally:
        speaker.close()
