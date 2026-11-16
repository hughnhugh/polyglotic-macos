"""Finished speech not yet answered (connection.unanswered): kept until its
answer, sent again after a reconnect, bounded in time and size."""

from polyglotic_desktop.connection.unanswered import GivenUp, Handed, UnansweredSpeech


class Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_kept_until_answered() -> None:
    kept = UnansweredSpeech(Clock())
    kept.sending("a", (), b"A")
    kept.sending("b", (), b"B")
    assert kept.to_send_again() == [b"A", b"B"]
    assert kept.to_send_again() == [b"A", b"B"]  # still kept until answered
    kept.answered("a")
    assert kept.to_send_again() == [b"B"]
    kept.answered("nobody")
    assert len(kept) == 1
    assert "b" in kept and "a" not in kept


def test_speech_overtaken_by_a_later_answer_is_given_up_after_a_while() -> None:
    """polyglotic-hq 271: the server answers finished speech in order, so
    "a", unanswered when "b" (sent after it) is answered, was lost there."""
    clock = Clock()
    kept = UnansweredSpeech(clock)
    kept.sending("a", (), b"A")
    kept.sending("b", (), b"B")
    kept.sending("c", (), b"C")
    kept.answered("b")
    assert kept.give_up(after=8.0) == []  # not yet: it has waited no time
    clock.now += 8
    assert kept.give_up(after=8.0) == [("a", GivenUp.OVERTAKEN)]
    assert kept.to_send_again() == [b"C"]  # sent after "b": still awaited
    assert kept.waiting_since() == 100.0


def test_speech_older_than_the_keep_time_is_given_up() -> None:
    clock = Clock()
    kept = UnansweredSpeech(clock, keep_sec=120)
    kept.sending("a", (), b"A")
    clock.now += 121
    kept.sending("b", (), b"B")
    assert kept.give_up(after=8.0) == [("a", GivenUp.TOO_OLD)]
    assert kept.waiting_since() == 221.0


def test_sent_again_on_a_new_session_speech_is_no_longer_overtaken() -> None:
    clock = Clock()
    kept = UnansweredSpeech(clock)
    kept.sending("a", (), b"A")
    kept.sending("b", (), b"B")
    kept.answered("b")
    assert kept.to_send_again() == [b"A"]  # the connection dropped
    clock.now += 30
    assert kept.give_up(after=8.0) == []


def test_a_caption_the_app_withdraws_isnt_waited_for() -> None:
    kept = UnansweredSpeech(Clock())
    kept.sending("a", (), b"A")
    kept.withdrawn("a")
    assert len(kept) == 0


def test_a_join_replaces_the_earlier_frames_and_keeps_the_first_time() -> None:
    clock = Clock()
    kept = UnansweredSpeech(clock, keep_sec=10)
    kept.sending("a", (), b"A")
    kept.sending("live", (), b"L")
    clock.now += 8
    kept.sending("a", ("live",), b"A+L")  # the joined caption
    assert kept.to_send_again() == [b"A+L"]
    clock.now += 3  # 11s since "a" was first sent
    assert kept.to_send_again() == []


def test_an_answer_for_a_joined_caption_answers_those_it_replaces() -> None:
    kept = UnansweredSpeech(Clock())
    kept.sending("a", (), b"A")
    kept.sending("b", (), b"B")
    kept.answered("c", replaces=("a", "b"))
    assert kept.to_send_again() == []


def test_too_old_or_too_much_is_dropped_oldest_first() -> None:
    clock = Clock()
    kept = UnansweredSpeech(clock, keep_sec=60, max_bytes=5)
    kept.sending("a", (), b"AA")
    kept.sending("b", (), b"BB")
    kept.sending("c", (), b"CC")
    assert kept.to_send_again() == [b"BB", b"CC"]
    clock.now += 61
    assert kept.to_send_again() == []


def test_kept_through_a_two_minute_outage_like_a_resumed_session() -> None:
    """polyglotic-hq 165: as long as the server keeps a lost session to resume
    (its decision 0040), 120s - a 2-minute outage's last caption still goes."""
    clock = Clock()
    kept = UnansweredSpeech(clock)
    kept.sending("c1", (), b"one")
    clock.now += 110.0
    assert kept.to_send_again() == [b"one"]
    clock.now += 11.0
    assert kept.to_send_again() == []


def test_a_closed_session_hands_its_unanswered_speech_to_the_next() -> None:
    """polyglotic-hq 277: what one session never had answered goes to the
    next, oldest first, with when it was first sent - forgotten by the
    first; the next keeps it after its own, and gives it up on time."""
    clock = Clock()
    old, new = UnansweredSpeech(clock), UnansweredSpeech(clock)
    old.sending("a", (), b"A")
    clock.now += 5
    old.sending("b", (), b"B")
    new.sending("c", (), b"C")  # the new session's own, sent already
    handed = old.hand_over()
    assert handed == [Handed("a", b"A", 100.0), Handed("b", b"B", 105.0)]
    assert len(old) == 0 and old.hand_over() == []
    new.take_on(handed)
    assert new.to_send_again() == [b"C", b"A", b"B"]
    assert new.waiting_since() == 100.0  # waited from when first sent
    new.answered("a")
    assert new.to_send_again() == [b"C", b"B"]
    clock.now += 121  # "b" and "c" both first sent at 105: now too old
    assert new.give_up(after=8.0) == [
        ("c", GivenUp.TOO_OLD),
        ("b", GivenUp.TOO_OLD),
    ]


def test_too_old_is_not_handed_over() -> None:
    clock = Clock()
    old = UnansweredSpeech(clock)
    old.sending("a", (), b"A")
    clock.now += 121
    old.sending("b", (), b"B")
    assert old.hand_over() == [Handed("b", b"B", 221.0)]
