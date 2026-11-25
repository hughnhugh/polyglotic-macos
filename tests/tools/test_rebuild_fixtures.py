"""The rebuild fixtures remain exact recordings of today's caption model."""

from tools.rebuild_fixtures.record import FIXTURES, record, specs


def test_every_rebuild_fixture_is_current() -> None:
    import json

    found = {path.stem for path in FIXTURES.glob("*.json")}
    expected = {spec.name for spec in specs()}
    assert found == expected
    for spec in specs():
        saved = json.loads((FIXTURES / f"{spec.name}.json").read_text(encoding="utf-8"))
        assert saved == record(spec), spec.name


def test_acceptance_scenarios_are_separate_and_complete() -> None:
    fixtures = specs()
    assert len(fixtures) >= 12
    assert {fixture.mode for fixture in fixtures} >= {
        "video-instant",
        "video-scrolling",
    }
    assert {
        (fixture.target, fixture.events[0][1]["language"]) for fixture in fixtures
    } >= {("en", "zh"), ("zh", "en"), ("en", "ja")}
