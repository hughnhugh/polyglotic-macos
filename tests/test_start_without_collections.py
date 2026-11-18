"""The app's start holds Python's garbage collector off until its window has
painted (decision 0233, polyglotic-hq 509): collections set off by the
start's tens of thousands of new objects went through every object the
imports had made - 26-32 ms of the start with 30,000 words met on the
second PC. It's on again once the window has painted, and whichever way the
start ends: a second copy's exit, a check's, a start that fails."""

import gc

import pytest

from polyglotic_desktop import main as app


def test_the_collector_is_off_until_the_window_has_painted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[bool] = []

    def start_and_run(argv: list[str] | None, shown: object) -> None:
        seen.append(gc.isenabled())  # building the window
        assert callable(shown)
        shown()  # its first paint
        seen.append(gc.isenabled())  # the app running

    monkeypatch.setattr(app, "_start_and_run", start_and_run)
    app.main([])
    assert seen == [False, True]
    assert gc.isenabled()


@pytest.mark.parametrize("ending", [SystemExit(0), RuntimeError("a fault")])
def test_the_collector_is_on_again_however_the_start_ends(
    monkeypatch: pytest.MonkeyPatch, ending: BaseException
) -> None:
    def start_and_run(argv: list[str] | None, shown: object) -> None:
        raise ending

    monkeypatch.setattr(app, "_start_and_run", start_and_run)
    with pytest.raises(type(ending)):
        app.main([])
    assert gc.isenabled()


def test_a_collector_turned_off_before_stays_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whoever turned it off (a budget test's `sampled`) turns it on."""
    monkeypatch.setattr(app, "_start_and_run", lambda argv, shown: shown())
    gc.disable()
    try:
        app.main([])
        assert not gc.isenabled()
    finally:
        gc.enable()
