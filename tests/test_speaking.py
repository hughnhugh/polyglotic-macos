"""The `Speaker` port on its own thread (`platform.speaking`, polyglotic-hq
286): the voices listed in the background and looked for again when old, a
word made and played with its silence trimmed, `sounding` told as its sound
starts, `ended` told once - heard to its end, stopped, replaced, or failed -
and ten fast clicks saying only the last. A reading (polyglotic-hq 495): a
chunk at a time, each hushed on its own, each word told as it sounds, and
stopped by a word or a stop. Stand-ins for the OS's voices and output:
nothing is played."""

import io
import struct
import sys
import threading
import time
import wave

import pytest

from polyglotic_desktop.platform.speaking import (
    CHUNK_PAUSE_SEC,
    LEAD_SEC,
    SILENT,
    TAIL_SEC,
    VOICES_STALE_SEC,
    Clip,
    SpeakerThread,
    WordTime,
    clip_of_wav,
    trimmed,
)
from polyglotic_desktop.ports.speaker import Voice

RATE = 16_000
HUIHUI = Voice("zh-1", "Microsoft Huihui", "zh-CN")


def clip(silence_before: float, sound: float, silence_after: float) -> Clip:
    frames = [0] * round(silence_before * RATE)
    frames += [8000 if i % 2 else -8000 for i in range(round(sound * RATE))]
    frames += [0] * round(silence_after * RATE)
    return Clip(struct.pack(f"<{len(frames)}h", *frames), RATE)


class Voices:
    """The OS's voices: a word takes `making` seconds to make."""

    def __init__(self, making: float = 0.0, length: float = 0.3) -> None:
        self.listed = 0
        self.installed: tuple[Voice, ...] = (HUIHUI,)
        self.made: list[tuple[str, str, float]] = []
        self.making = making
        self.length = length
        self.fail = False

    def found(self) -> tuple[Voice, ...]:
        self.listed += 1
        return self.installed

    def synthesize(self, text: str, voice: Voice, rate: float) -> Clip:
        time.sleep(self.making)
        if self.fail:
            raise OSError("the voice isn't installed any more")
        self.made.append((text, voice.id, rate))
        return clip(0.15, self.length, 0.2)


class Output:
    """The OS's output: plays for the clip's length, unless it never ends."""

    made: list["Output"]

    def __init__(self, endless: bool = False, works: bool = True) -> None:
        self.endless = endless
        self.works = works
        self.clip: Clip | None = None
        self.until = 0.0
        self.stopped = False

    def start(self, clip: Clip) -> bool:
        self.clip = clip
        self.until = time.perf_counter() + clip.seconds
        return self.works

    def playing(self) -> bool:
        return self.endless or time.perf_counter() < self.until

    def stop(self) -> None:
        self.stopped = True


class Heard:
    """What `sounding` and `ended` were told, by word."""

    def __init__(self) -> None:
        self.sounding: list[tuple[str, float, float]] = []
        self.ended: list[tuple[str, bool]] = []
        self.threads: set[str] = set()
        self.done = threading.Event()

    def say(self, speaker: SpeakerThread, text: str, rate: float = 1.0) -> None:
        def sounding(start: float, seconds: float) -> None:
            self.threads.add(threading.current_thread().name)
            self.sounding.append((text, start, seconds))

        def ended(heard: bool) -> None:
            self.threads.add(threading.current_thread().name)
            self.ended.append((text, heard))
            self.done.set()

        speaker.say(text, HUIHUI, rate, sounding, ended)


def wait_until(condition: object, timeout: float = 3.0) -> None:
    give_up = time.monotonic() + timeout
    while not condition():  # type: ignore[operator]
        assert time.monotonic() < give_up, "never happened"
        time.sleep(0.005)


@pytest.fixture
def outputs() -> list[Output]:
    return []


def speaker_with(
    voices: Voices, outputs: list[Output], **output: bool
) -> SpeakerThread:
    def new_output() -> Output:
        made = Output(**output)
        outputs.append(made)
        return made

    return SpeakerThread(voices, new_output)


def test_a_word_is_said_trimmed_and_told_from_the_speakers_thread(
    outputs: list[Output],
) -> None:
    voices = Voices()
    speaker = speaker_with(voices, outputs)
    heard = Heard()
    try:
        before = time.perf_counter()
        heard.say(speaker, "你好", 0.7)
        assert heard.done.wait(3)
        assert voices.made == [("你好", "zh-1", 0.7)]
        assert heard.ended == [("你好", True)]
        [(text, start, seconds)] = heard.sounding
        assert text == "你好" and start >= before
        # the voice's 0.15 s before and 0.2 s after trimmed to LEAD and TAIL
        assert seconds == pytest.approx(0.3 + LEAD_SEC + TAIL_SEC, abs=0.002)
        assert outputs[0].clip is not None and outputs[0].stopped  # device let go
        assert heard.threads == {"speaker"}
    finally:
        speaker.close()


def test_a_click_while_it_speaks_stops_it(outputs: list[Output]) -> None:
    speaker = speaker_with(Voices(length=5.0), outputs)
    heard = Heard()
    try:
        heard.say(speaker, "电脑")
        wait_until(lambda: heard.sounding)
        speaker.stop()
        assert heard.done.wait(1)
        assert heard.ended == [("电脑", False)]
        assert outputs[0].stopped
    finally:
        speaker.close()


def test_ten_fast_clicks_say_only_the_last_and_end_every_other(
    outputs: list[Output],
) -> None:
    voices = Voices(making=0.05)
    speaker = speaker_with(voices, outputs)
    heard = Heard()
    try:
        for n in range(10):
            heard.say(speaker, f"word {n}")
        wait_until(lambda: len(heard.ended) == 10)
        assert dict(heard.ended)["word 9"] is True
        assert sorted(t for t, ok in heard.ended if not ok) == [
            f"word {n}" for n in range(9)
        ]
        # at most the first, already being made, and the last were made
        assert len(voices.made) <= 2 and voices.made[-1][0] == "word 9"
        assert [s[0] for s in heard.sounding][-1] == "word 9"
    finally:
        speaker.close()


def test_a_new_word_while_one_plays_stops_that_one(outputs: list[Output]) -> None:
    speaker = speaker_with(Voices(length=5.0), outputs)
    heard = Heard()
    try:
        heard.say(speaker, "one")
        wait_until(lambda: heard.sounding)
        heard.say(speaker, "two")
        wait_until(lambda: len(heard.sounding) == 2)
        speaker.stop()
        wait_until(lambda: len(heard.ended) == 2)
        assert heard.ended == [("one", False), ("two", False)]
    finally:
        speaker.close()


def test_a_word_that_cant_be_made_or_played_ends_false(outputs: list[Output]) -> None:
    voices = Voices()
    voices.fail = True
    speaker = speaker_with(voices, outputs)
    heard = Heard()
    try:
        heard.say(speaker, "gone")
        assert heard.done.wait(2)
        assert heard.ended == [("gone", False)] and heard.sounding == []
    finally:
        speaker.close()
    no_device = speaker_with(Voices(), outputs, works=False)
    heard = Heard()
    try:
        heard.say(no_device, "nowhere")
        assert heard.done.wait(2)
        assert heard.ended == [("nowhere", False)] and heard.sounding == []
    finally:
        no_device.close()


def test_an_output_that_never_ends_is_given_up_on(
    monkeypatch: pytest.MonkeyPatch, outputs: list[Output]
) -> None:
    from polyglotic_desktop.platform import speaking

    monkeypatch.setattr(speaking, "OVERRUN_SEC", 0.1)
    speaker = speaker_with(Voices(length=0.1), outputs, endless=True)
    heard = Heard()
    try:
        heard.say(speaker, "stuck")
        assert heard.done.wait(2)
        assert heard.ended == [("stuck", False)] and outputs[0].stopped
    finally:
        speaker.close()


def test_the_voices_are_listed_only_once_asked_never_at_the_start() -> None:
    """Made at the app's start, the speaker lists nothing until asked - the
    start's budget never waits on Windows' speech - then in the
    background: the first ask answers at once, with none yet."""
    for ask in ("voices", "look_for_voices"):
        voices = Voices()
        speaker = SpeakerThread(voices, Output)
        try:
            time.sleep(0.05)
            assert voices.listed == 0 and not speaker.listed
            answer = getattr(speaker, ask)()
            assert answer in (None, ())
            wait_until(lambda: speaker.listed)  # noqa: B023
            assert speaker.voices() == (HUIHUI,) and voices.listed == 1
        finally:
            speaker.close()


def test_the_voices_are_listed_in_the_background_and_again_when_old() -> None:
    now = [100.0]
    voices = Voices()
    speaker = SpeakerThread(voices, Output, clock=lambda: now[0])
    try:
        speaker.look_for_voices()
        wait_until(lambda: speaker.listed)
        assert speaker.voices() == (HUIHUI,) and voices.listed == 1
        added = Voice("vi-1", "Microsoft An", "vi-VN")
        voices.installed = (HUIHUI, added)  # added in Windows' settings
        assert speaker.voices() == (HUIHUI,)  # not old yet: not looked for
        now[0] += VOICES_STALE_SEC + 1
        assert speaker.voices() == (HUIHUI,)  # at once; looked for behind
        wait_until(lambda: speaker.voices() == (HUIHUI, added))
        assert voices.listed == 2
    finally:
        speaker.close()


def test_closing_ends_what_waits() -> None:
    gate = threading.Event()

    class Slow(Voices):
        def synthesize(self, text: str, voice: Voice, rate: float) -> Clip:
            gate.wait(2)
            return super().synthesize(text, voice, rate)

    speaker = SpeakerThread(Slow(), Output)
    heard = Heard()
    heard.say(speaker, "first")
    heard.say(speaker, "waiting")
    speaker.close(timeout=0.05)
    gate.set()
    speaker.close()
    assert sorted(heard.ended) == [("first", False), ("waiting", False)]


def test_silence_is_trimmed_to_lead_and_tail() -> None:
    cut = trimmed(clip(0.15, 0.4, 0.3))
    assert cut.seconds == pytest.approx(0.4 + LEAD_SEC + TAIL_SEC, abs=0.001)
    samples = struct.unpack(f"<{cut.frames}h", cut.pcm)
    lead = round(LEAD_SEC * RATE)
    assert all(abs(s) <= SILENT for s in samples[:lead]) and abs(samples[lead]) > SILENT
    quiet = clip(0.2, 0.0, 0.0)
    assert trimmed(quiet) == quiet  # nothing loud: as it is
    loud = clip(0.0, 0.2, 0.0)
    assert trimmed(loud).seconds == pytest.approx(0.2, abs=0.001)


def test_a_wav_is_read_as_16_bit_pcm() -> None:
    data = io.BytesIO()
    with wave.open(data, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(clip(0.0, 0.1, 0.0).pcm)
    read = clip_of_wav(data.getvalue())
    assert (read.rate, read.channels, read.frames) == (RATE, 1, 1600)
    with pytest.raises(ValueError):
        clip_of_wav(b"not a wav")


# -- a reading (polyglotic-hq 495) ---------------------------------------------------------


class Timed(Voices):
    """Voices that say when each word sounds: a word every 0.1 s, from the
    0.15 s of silence the voice puts first."""

    def synthesize(self, text: str, voice: Voice, rate: float) -> Clip:
        made = super().synthesize(text, voice, rate)
        starts = [
            i for i, c in enumerate(text) if c != " " and (not i or text[i - 1] == " ")
        ]
        words = tuple(
            WordTime(a, text.find(" ", a) % (len(text) + 1), 0.15 + 0.1 * n)
            for n, a in enumerate(starts)
        )
        return Clip(made.pcm, made.rate, made.channels, words)


class Read:
    """What a reading told: sounding, spoken and ended, with the times."""

    def __init__(self) -> None:
        self.sounding: list[tuple[float, float]] = []
        self.spoken: list[tuple[int, int, int, float]] = []
        self.ended: list[bool] = []
        self.done = threading.Event()

    def read(self, speaker: SpeakerThread, *chunks: str) -> None:
        def ended(heard: bool) -> None:
            self.ended.append(heard)
            self.done.set()

        speaker.read(
            chunks,
            HUIHUI,
            1.0,
            lambda start, seconds: self.sounding.append((start, seconds)),
            ended,
            lambda c, a, b: self.spoken.append((c, a, b, time.perf_counter())),
        )


def test_a_reading_is_said_a_chunk_at_a_time_each_hushed_on_its_own(
    outputs: list[Output],
) -> None:
    voices = Voices(length=0.2)
    speaker = speaker_with(voices, outputs)
    read = Read()
    try:
        read.read(speaker, "一七六七年。", "第一条全铁轨道问世。", "完。")
        assert read.done.wait(3)
        assert [m[0] for m in voices.made] == [
            "一七六七年。",
            "第一条全铁轨道问世。",
            "完。",
        ]
        assert read.ended == [True]
        assert len(read.sounding) == 3 and len(outputs) == 3
        for (start, seconds), (after, _) in zip(
            read.sounding, read.sounding[1:], strict=False
        ):
            assert after >= start + seconds + CHUNK_PAUSE_SEC  # one after another
        # no word times: each chunk lit whole as it starts
        assert [s[:3] for s in read.spoken] == [(0, 0, 6), (1, 0, 10), (2, 0, 2)]
    finally:
        speaker.close()


@pytest.mark.xfail(
    sys.platform == "darwin",
    reason="polyglotic-hq 523: on GitHub's Mac a word is told 0.10-0.17 s late"
    " (runs 44269898527, 44605554270) against 0.08 s allowed - the speaker's"
    " 20 ms waits oversleep there; making the next chunk takes 0.5 ms, so it's"
    " the runner's timers, not this code. Whether a learner's Mac is late too"
    " is a proposed check.",
    strict=False,
)
def test_each_word_is_told_as_it_sounds(outputs: list[Output]) -> None:
    speaker = speaker_with(Timed(length=0.5), outputs)
    read = Read()
    try:
        read.read(speaker, "the giant turtle", "eats")
        assert read.done.wait(3)
        assert [s[:3] for s in read.spoken] == [
            (0, 0, 3), (0, 4, 9), (0, 10, 16), (1, 0, 4)
        ]  # fmt: skip
        [(first, _), (second, _)] = read.sounding
        # the voice's 0.15 s of silence trimmed to LEAD: its words move with it
        for (_, _, _, at), due in zip(
            read.spoken, (first, first + 0.1, first + 0.2, second), strict=True
        ):
            assert due + LEAD_SEC - 0.01 <= at <= due + LEAD_SEC + 0.08
    finally:
        speaker.close()


def test_a_reading_stopped_half_way_hushes_no_more(outputs: list[Output]) -> None:
    voices = Voices(length=1.0)
    speaker = speaker_with(voices, outputs)
    read = Read()
    try:
        read.read(speaker, "one.", "two.", "three.")
        wait_until(lambda: read.sounding)
        speaker.stop()
        assert read.done.wait(2)
        assert read.ended == [False]
        assert len(read.sounding) == 1  # the next chunk was never heard
        assert "three." not in [m[0] for m in voices.made]
    finally:
        speaker.close()


def test_a_word_stops_a_reading_and_a_reading_stops_a_word(
    outputs: list[Output],
) -> None:
    speaker = speaker_with(Voices(length=2.0), outputs)
    read, heard = Read(), Heard()
    try:
        read.read(speaker, "one.", "two.")
        wait_until(lambda: read.sounding)
        heard.say(speaker, "你好")  # the lookup card's "say it"
        assert read.done.wait(2) and read.ended == [False]
        wait_until(lambda: heard.sounding)
        again = Read()
        again.read(speaker, "three.")
        assert heard.done.wait(2) and heard.ended == [("你好", False)]
        speaker.stop()
        assert again.done.wait(2)
    finally:
        speaker.close()


def test_word_times_move_with_the_trimmed_start() -> None:
    made = clip(0.15, 0.4, 0.3)
    timed = Clip(made.pcm, made.rate, words=(WordTime(0, 2, 0.15), WordTime(3, 5, 0.4)))
    cut = trimmed(timed)
    assert [(w.start, w.end) for w in cut.words] == [(0, 2), (3, 5)]
    assert [w.at for w in cut.words] == pytest.approx(
        [LEAD_SEC, 0.25 + LEAD_SEC], abs=0.001
    )


def test_a_reading_said_again_is_played_from_memory(outputs: list[Output]) -> None:
    voices = Voices(length=0.05)
    speaker = speaker_with(voices, outputs)
    try:
        for _ in range(2):
            read = Read()
            read.read(speaker, "one.", "two.")
            assert read.done.wait(2) and read.ended == [True]
        assert [m[0] for m in voices.made] == ["one.", "two."]  # made once
        heard = Heard()
        for _ in range(2):  # a word is made each time: its recording may arrive
            heard.done.clear()
            heard.say(speaker, "one.")
            assert heard.done.wait(2)
        assert [m[0] for m in voices.made] == ["one.", "two.", "one.", "one."]
    finally:
        speaker.close()
