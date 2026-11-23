"""The shared panels' states (polyglotic-hq project 109's structure,
section 4), held to their budgets: Languages as Settings > Captions'
Speech and in a transcript's rail ("This window"), Timing with Live
updates, the look's groups in a rail - and a change made in one panel
reaching every panel and three caption windows (a click: 30 ms).

Each panel is photographed at a width it gets: half of a 720 px column,
or the 320 px rail (both grow with the text size: `--text-size`). The
theme is today's default (Margin, dark), from today's theme module, as
`main` hands it over.
"""

from collections.abc import Callable
from dataclasses import asdict, replace

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from polyglotic_desktop.core.lexicon.pack_download import PackProgress, Problem, Step
from polyglotic_desktop.core.listening.display import WordLinks
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import OFFERED_MODES, CaptionMode
from polyglotic_desktop.perf import budgets
from polyglotic_desktop.ui import theme as todays_theme
from polyglotic_desktop.ui.recorded_captions import APP, MIC
from polyglotic_desktop.ui_next import style
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.face_rows import FacesPanel
from polyglotic_desktop.ui_next.panels import (
    BehaviourPanel,
    LanguagesPanel,
    LookPanel,
    ResetCard,
    TimingPanel,
    WordLinksPanel,
)
from polyglotic_desktop.ui_next.transcript_window import SettingsRail
from polyglotic_desktop.ui_next.views.caption_window import CaptionLook
from polyglotic_desktop.ui_next.views.panels import (
    DownloadsView,
    FaceDownloads,
    LanguagesView,
    LookView,
    SessionLanguages,
    Timing,
    TimingView,
    WindowLanguage,
    WindowLanguageView,
)
from polyglotic_desktop.ui_next.views.transcript import RAIL_WIDTH
from tools.ui_lab.caption_window import LABELS, _areas
from tools.ui_lab.lab import Lab, State
from tools.ui_lab.new_parts import finished

HALF = 352
"""A panel's width beside another in Home's 720 px column."""
RAIL = 320


def margin_dark() -> style.Theme:
    """Today's default window theme, as `main` hands it to the new interface."""
    palette = todays_theme.palette("dark", todays_theme.DEFAULT_THEME)
    family = todays_theme.THEMES[todays_theme.DEFAULT_THEME].heading_family
    return style.Theme(asdict(palette), family, dark=True)


def page(lab: Lab, width: int, *panels: QWidget) -> QWidget:
    """`panels` side by side in a window dressed in the theme."""
    theme = margin_dark()
    style.use(theme)
    shown = QWidget()
    shown.setObjectName("Content")
    shown.setStyleSheet(style.stylesheet(theme))
    row = QHBoxLayout(shown)
    row.setContentsMargins(16, 16, 16, 16)
    row.setSpacing(16)
    for panel in panels:
        column = QVBoxLayout()
        column.addWidget(panel)
        column.addStretch(1)
        row.addLayout(column)
        panel.setFixedWidth(width)
    shown.show()
    lab.pump()
    fits(shown)
    lab.pump()
    return shown


def fits(shown: QWidget) -> None:
    """`shown` as tall as its wrapped words need at its width (a window
    sizes itself from its layout's height, not its height for a width)."""
    layout = shown.layout()
    shown.adjustSize()
    if layout is not None and layout.hasHeightForWidth():
        shown.resize(shown.width(), layout.totalHeightForWidth(shown.width()))


SESSION = SessionLanguages(
    second_languages={"en": "zh"},
    spelling_hints=("Caleb", "HSK"),
    in_use=("en", "ja"),
)


def speech(lab: Lab) -> QWidget:
    """Settings > Captions' Speech: the session's languages, without
    what's learned or live translation (261)."""
    view = LanguagesView(SESSION)
    panel = LanguagesPanel(view, speech=True)
    shown = page(lab, style.px(HALF), panel)
    lab.time(
        "spoken_language",
        lambda: panel.spoken.choose("zh" if view.value.spoken != "zh" else None),
        repeat=6,
        budget=budgets.CLICK,
    )
    panel.spoken.choose(None)
    lab.pump()
    return shown


def languages_this_window(lab: Lab) -> QWidget:
    view = LanguagesView(SESSION)
    own = WindowLanguageView(WindowLanguage("Discord", "en", show_mic=True))
    panel = LanguagesPanel(view, own)
    shown = page(lab, style.px(RAIL), panel)
    lab.time(
        "show_my_speech",
        lambda: panel.show_mic.click() if panel.show_mic else None,
        repeat=6,
        budget=budgets.CLICK,
    )
    return shown


def timing(mode: CaptionMode, value: Timing | None = None) -> Callable[[Lab], QWidget]:
    """The Timing panel on `mode`: under the choice, only that timing's own
    settings, in seconds (295) - at `value` if given."""

    def run(lab: Lab) -> QWidget:
        view = TimingView(value or Timing(mode, 1.5))
        panel = TimingPanel(view)
        shown = page(lab, style.px(HALF), panel)
        modes = list(OFFERED_MODES)
        lab.time(
            "caption_timing",
            lambda: panel.mode.choose(modes[(modes.index(view.value.mode) + 1) % 4]),
            repeat=6,
            budget=budgets.CLICK,
        )
        panel.mode.choose(mode)
        lab.pump()
        return shown

    return run


def look_rail(lab: Lab) -> QWidget:
    """The look's groups in a transcript's rail as it is (356 px, its
    scrollbar shown), one under the other, their lines on hover (176)."""
    theme = margin_dark()
    style.use(theme)
    view = LookView(CaptionLook())
    rail = SettingsRail()
    rail.setStyleSheet(style.stylesheet(theme))
    for group in (
        LookPanel(view),
        WordLinksPanel(view),
        BehaviourPanel(view),
        ResetCard(view),
    ):
        rail.add_panel(group)
    rail.setFixedSize(style.px(RAIL_WIDTH), style.px(900))  # a window of its own here
    rail.show()
    lab.pump()
    lab.time(
        "show_source",
        lambda: view.set_show_source(not view.value.show_source),
        repeat=6,
        budget=budgets.CLICK,
    )
    view.set_show_source(True)
    lab.pump()
    return rail


def fonts_card(lab: Lab) -> QWidget:
    """Settings > Look's Fonts card (polyglotic-hq 482): a row for each
    language captioned - Chinese spoken, Thai and Arabic heard lately, the
    windows in English and Hindi, Russian a second language - each on its
    default, Chinese's chosen from this PC's own."""
    look = LookView(CaptionLook(faces=(("zh", "Microsoft YaHei UI"),)))
    languages = LanguagesView(
        SessionLanguages(
            spoken="zh",
            recent_spoken=("th", "ar"),
            in_use=("en", "hi"),
            second_languages={"en": "ru"},
        )
    )
    panel = FacesPanel(look, languages, notes=True)
    shown = page(lab, style.px(HALF + 120), panel)
    lab.time(
        "face",
        lambda: look.set_face(
            "th", None if dict(look.value.faces).get("th") else "Leelawadee UI"
        ),
        repeat=6,
        budget=budgets.CLICK,
    )
    look.set_face("th", None)
    lab.pump()
    shown.keep = (look, languages)  # type: ignore[attr-defined]
    return shown


def fonts_downloading(lab: Lab) -> QWidget:
    """The Fonts card while faces come down (polyglotic-hq 482): Mandarin in
    Traditional characters, its default LXGW WenKai TC downloading (532); Japanese on
    Klee One, chosen, paused on a metered connection; Cantonese on its
    default, here; the others' sizes in their lists."""
    look = LookView(CaptionLook(faces=(("ja", "Klee One Captions"),)))
    languages = LanguagesView(
        SessionLanguages(
            spoken="zh", in_use=("ja", "yue"), mandarin_script="traditional"
        )
    )
    sizes = {"lxgwwenkaitc": 4_210_000, "kleeone": 3_500_000, "notoseriftc": 4_080_000}
    downloads = DownloadsView(
        FaceDownloads(
            sizes=sizes,
            here=frozenset({"notosanshk"}),
            progress={
                "lxgwwenkaitc": PackProgress(
                    "font:lxgwwenkaitc", Step.DOWNLOADING, 1_400_000, 4_210_000
                ),
                "kleeone": PackProgress(
                    "font:kleeone",
                    Step.DOWNLOADING,
                    0,
                    3_500_000,
                    problem=Problem.METERED,
                ),
            },
        )
    )
    panel = FacesPanel(look, languages, downloads, notes=True)
    shown = page(lab, style.px(HALF + 120), panel)
    shown.keep = (look, languages, downloads)  # type: ignore[attr-defined]
    return shown


def change_everywhere(lab: Lab) -> QWidget:
    """Home's Look panel and a rail's, bound to one view that three caption
    windows follow: a change in one panel, timed until the other panel and
    every window have it."""
    windows = CaptionWindows(None, MIC, _areas)
    windows.set_labels(LABELS, "You")
    sources = [APP, SourceId("app-2"), SourceId("app-3")]
    windows.set_captioned([(f"app{n}", s) for n, s in enumerate(sources)])
    for source in sources:
        for update in finished(150, source):
            windows.apply(update)
    lab.closing.append(windows.close)
    view = LookView(windows.look, on_change=windows.set_look)
    home, rail = LookPanel(view, notes=True), LookPanel(view)
    home_links, rail_links = WordLinksPanel(view, notes=True), WordLinksPanel(view)
    shown = page(lab, style.px(HALF), home, home_links, rail, rail_links)
    links = [WordLinks.OFF, WordLinks.HOVER]
    lab.time(
        "word_links",
        lambda: home_links.word_links.choose(
            links[view.value.word_links is WordLinks.OFF]
        ),
        repeat=6,
        budget=budgets.CLICK,
    )
    lab.time(
        "show_original",
        lambda: home.original.click(),
        repeat=6,
        budget=budgets.CLICK,
    )
    lab.time(
        "background",
        lambda: home.background.setValue(home.background.value() - 5),
        repeat=6,
        budget=budgets.CLICK,
    )
    lab.time(
        "colour",
        lambda: view.set_colour(
            "translation",
            "#7fe3ff" if view.value.translation != "#7fe3ff" else "#ffd76e",
        ),
        repeat=6,
        budget=budgets.CLICK,
    )
    lab.time(
        "font",
        lambda: view.set_face(
            "zh", None if dict(view.value.faces).get("zh") else "Microsoft YaHei UI"
        ),
        repeat=4,
        budget=budgets.DISPLAY_CHANGE,
    )
    assert rail_links.word_links.value() == view.value.word_links
    assert rail.original.isChecked() == view.value.show_original
    assert all(w.look == view.value for w in windows.windows.values())
    view.change(replace(view.value, show_original=True, faces=()))
    lab.pump()
    return shown


STATES = [
    State(f"ui_next.panel_{name}", run, gated=True)
    for name, run in (
        ("speech", speech),
        ("languages_this_window", languages_this_window),
        ("timing_steady", timing(CaptionMode.WHOLE)),
        ("timing_words", timing(CaptionMode.STEADY)),
        ("timing_calm", timing(CaptionMode.CALM)),
        ("timing_live", timing(CaptionMode.INSTANT)),
        # Live updates every 6 s, the longest wait 3 s: the 3 s is followed,
        # and the panel says so (295)
        (
            "timing_live_slower",
            timing(CaptionMode.INSTANT, Timing(CaptionMode.INSTANT, 6.0)),
        ),
        ("look_rail", look_rail),
        ("change_everywhere", change_everywhere),
        ("fonts", fonts_card),
        ("fonts_downloading", fonts_downloading),
    )
]
