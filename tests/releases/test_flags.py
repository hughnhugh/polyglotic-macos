"""The app's feature flags (polyglotic-hq ENGINEERING.md, "Feature
flags"; decision 0263): each declared once, with an owner and an expiry
date, and this test fails once one is past it - so its flag, or the code
behind it, goes."""

from datetime import date

from polyglotic_desktop.core.releases import flags


def test_every_flag_is_declared_once_with_an_owner() -> None:
    names = [flag.name for flag in flags.DECLARED]
    assert len(names) == len(set(names))
    assert all(flag.owner and flag.description for flag in flags.DECLARED)


def test_no_flag_is_past_its_expiry() -> None:
    expired = [f.name for f in flags.DECLARED if f.expires < date.today()]
    assert not expired, f"remove these flags, or the code behind them: {expired}"


def test_a_flag_set_for_a_run_and_back_to_its_default() -> None:
    flag = flags.SPOKEN_NUDGE
    flags.set_value(flag, not flag.default)
    assert flags.on(flag) is not flag.default
    flags.set_value(flag, None)
    assert flags.on(flag) is flag.default
