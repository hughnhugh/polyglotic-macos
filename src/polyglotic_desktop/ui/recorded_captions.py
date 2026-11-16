"""Recorded caption updates: a made-up conversation, to see the caption
windows and the transcripts without the server (the UI lab, tests).

A developer's stand-in for the connection: what the server would send
for a few minutes of a Chinese video with the viewer talking over it in
English - live updates growing, finished captions with English
translations and word links, a join, a withdrawal (a phrase speech
models invent in near-silence), a live update whose
translation is still on its way (never blank), and the viewer's own mic
(already in English, so translated into the second language, Chinese).

Each entry is (seconds after the previous one, the update). Made-up text
only - never real calls.
"""

from polyglotic_desktop.core.listening.captions import (
    CaptionKind,
    CaptionUpdate,
    Clause,
    Language,
    WordLink,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import CaptionId, WithdrawalReason

ZH = Language("zh")
EN = Language("en")
APP = SourceId("app")
MIC = SourceId("mic")

Pair = tuple[str, str] | tuple[str, str, bool]


def clause(
    original: str,
    translation: str | None = None,
    pairs: tuple[Pair, ...] = (),
    into: Language = EN,
) -> Clause:
    """A clause with its translation into `into`, and word links between
    the words in `pairs` (original word, translated words, key link?),
    found by their first place in each text."""
    if translation is None:
        return Clause(original)
    links = []
    for pair in pairs:
        said, meant = pair[0], pair[1]
        key = pair[2] if len(pair) > 2 else True
        a = original.index(said)
        c = translation.index(meant)
        links.append(WordLink((a, a + len(said)), (c, c + len(meant)), bool(key), 0.9))
    return Clause(original, {into: translation}, {into: tuple(links)})


def _update(
    caption_id: str,
    kind: CaptionKind,
    clauses: tuple[Clause, ...],
    source: SourceId = APP,
    language: Language = ZH,
    replaces: tuple[str, ...] = (),
) -> CaptionUpdate:
    return CaptionUpdate(
        CaptionId(caption_id),
        source,
        kind,
        clauses,
        language,
        (language,),
        tuple(CaptionId(r) for r in replaces),
        processing_ms=400,
    )


def live(
    caption_id: str, *clauses: Clause, source: SourceId = APP, language: Language = ZH
) -> CaptionUpdate:
    return _update(caption_id, CaptionKind.LIVE, clauses, source, language)


def finished(
    caption_id: str,
    *clauses: Clause,
    source: SourceId = APP,
    language: Language = ZH,
    replaces: tuple[str, ...] = (),
) -> CaptionUpdate:
    return _update(
        caption_id, CaptionKind.FINISHED, clauses, source, language, replaces
    )


def withdrawn(caption_id: str, reason: WithdrawalReason) -> CaptionUpdate:
    return CaptionUpdate(
        CaptionId(caption_id), APP, CaptionKind.WITHDRAWN, reason=reason
    )


WEEKEND = clause(
    "我们周末一起去打游戏吧，",
    "Let's go play games together this weekend,",
    (
        ("周末", "weekend"),
        ("一起", "together"),
        ("打游戏", "play games"),
        ("我们", "Let's", False),
    ),
)
OKAY = clause("好不好？", "okay?", (("好不好", "okay"),))
FRUIT = clause(
    "超市的水果打折了，",
    "The fruit at the supermarket was on sale,",
    (("超市", "supermarket"), ("水果", "fruit"), ("打折", "on sale")),
)
BOUGHT = clause(
    "我买了很多。", "so I bought a lot.", (("买", "bought"), ("很多", "a lot"))
)
SATURDAY = clause(
    "Sounds good, see you Saturday.",
    "听起来不错，周六见。",
    (("Sounds good", "听起来不错"), ("Saturday", "周六"), ("see", "见")),
    into=ZH,
)
COMPUTER = clause(
    "我的电脑又卡了，",
    "My computer froze again,",
    (("电脑", "computer"), ("卡", "froze"), ("又", "again")),
)
RESTART = clause("我得重新启动。", "I have to restart it.", (("重新启动", "restart"),))
GAME = clause(
    "这个游戏的画面很漂亮，",
    "This game looks beautiful,",
    (("游戏", "game"), ("漂亮", "beautiful")),
)
CONTROLS = clause(
    "但是操作有点难。",
    "but the controls are a bit hard.",
    (("但是", "but"), ("操作", "controls"), ("有点", "a bit"), ("难", "hard")),
)


def recorded_captions() -> list[tuple[float, CaptionUpdate]]:
    """The conversation, as caption updates with the seconds between them."""
    return [
        (0.0, live("c1", clause("我们周末"))),
        (
            1.5,
            live(
                "c1",
                clause(
                    "我们周末一起去打游戏吧，",
                    "Let's go play games together this weekend,",
                ),
            ),
        ),
        (1.2, finished("c1", WEEKEND, OKAY)),
        (1.0, live("c2", clause("超市的水果", "The fruit at the supermarket"))),
        (1.5, finished("c2", FRUIT, BOUGHT)),
        (
            0.8,
            live(
                "y1",
                clause("Sounds good,", "听起来不错，", into=ZH),
                source=MIC,
                language=EN,
            ),
        ),
        (1.2, finished("y1", SATURDAY, source=MIC, language=EN)),
        (1.0, live("c3", clause("谢谢观看"))),
        (0.6, withdrawn("c3", WithdrawalReason.NEAR_SILENCE_PHRASE)),
        (1.0, finished("c4", COMPUTER)),
        (1.4, live("c5", clause("我得重新", "I have to re"))),
        # the same source again within 2s: a join, under the earlier id
        (1.0, finished("c4", COMPUTER, RESTART, replaces=("c5",))),
        (
            1.0,
            live("c6", clause("这个游戏的画面很漂亮，", "This game looks beautiful,")),
        ),
        # the next live update arrives before its translation: never blank
        (1.5, live("c6", clause("这个游戏的画面很漂亮，"), clause("但是操作"))),
        (1.2, finished("c6", GAME, CONTROLS)),
    ]
