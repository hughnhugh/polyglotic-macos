"""Caption faces downloaded on choice (polyglotic-hq 482, decision 0223):
published as riders of an entry in the signed list's `fonts`, read by an
app that knows them and ignored by one from before, downloaded as one
download with each step said, then added to Qt's fonts - and every caption
laid out again in them."""

import json
import threading
from pathlib import Path

import pytest
from tests.packs_server import StandIn
from tests.packs_storage import KEY, PRIVATE, PUBLIC
from tools.package import publish_packs

from polyglotic_desktop.adapters.pack_downloads import PackDeliveries, PackFolder
from polyglotic_desktop.adapters.pack_list import PackList, split_signed_list
from polyglotic_desktop.adapters.signed_feed import public_keys
from polyglotic_desktop.core.lexicon.pack_download import PackProgress, Step
from polyglotic_desktop.core.lexicon.packs import (
    FROM_SOURCE,
    Reader,
    read_fonts,
    read_pack_list,
    riders_wanted,
)
from polyglotic_desktop.ui_next import caption_faces

LIST = "packs/v1/list.signed"
READER = Reader(
    frozenset({"1"}), frozenset({"spaced"}), "0.1.8", frozenset({("font", "1")})
)
BEFORE = Reader(
    frozenset({"1"}), frozenset({"spaced"}), "0.1.7", frozenset({("audio", "1")})
)
FACE = caption_faces.FOLDER / "PTSans-Regular.ttf"
"""A real face to publish under a pack's name (PT Sans: what it is matters
not here, only that Qt reads it)."""


def built_faces(folder: Path, pack: str = "notoserifsc") -> Path:
    """What `tools.caption_fonts --packs` writes, for one face."""
    folder.mkdir(parents=True, exist_ok=True)
    files = [f"{pack}-upright-2026.11.18.ttf", f"{pack}-ofl-2026.11.18.txt"]
    (folder / files[0]).write_bytes(FACE.read_bytes())
    (folder / files[1]).write_text("SIL Open Font License 1.1\n", encoding="utf-8")
    manifest = [
        {
            "font": pack,
            "family": "PT Sans",
            "credits": "Its makers; OFL 1.1",
            "files": files,
        }
    ]
    (folder / "fonts.json").write_text(json.dumps(manifest), encoding="utf-8")
    return folder


def publish(monkeypatch: pytest.MonkeyPatch, out: Path, faces: Path) -> int:
    monkeypatch.setenv(publish_packs.KEY_VARIABLE, PRIVATE)
    previous = out.parent / "no-list.signed"
    previous.write_bytes(publish_packs.sign_list(publish_packs.list_bytes([], 1), KEY))
    return publish_packs.main(
        ["--fonts", str(faces), "--out", str(out), "--previous", str(previous)]
    )


@pytest.fixture
def bucket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    out = tmp_path / "bucket"
    assert publish(monkeypatch, out, built_faces(tmp_path / "built")) == 0
    return out


def listed(bucket: Path) -> bytes:
    return split_signed_list((bucket / LIST).read_bytes())[1]


# -- the list ------------------------------------------------------------------


def test_a_face_is_published_as_riders_of_its_entry_in_fonts(bucket: Path) -> None:
    data = listed(bucket)
    assert read_pack_list(data) == ((), 0)  # an app from before sees no change
    (face,) = read_fonts(data)
    assert (face.font, face.family) == ("notoserifsc", "PT Sans")
    assert [(r.kind, r.file, r.min_app) for r in face.riders] == [
        ("font", "notoserifsc-upright-2026.11.18.ttf", publish_packs.FONT_MIN_APP),
        ("font", "notoserifsc-ofl-2026.11.18.txt", publish_packs.FONT_MIN_APP),
    ]
    for rider in face.riders:
        packed = bucket / "packs" / "files" / rider.download
        assert packed.stat().st_size == rider.gz_size
    assert face.size(READER) == sum(r.gz_size for r in face.riders)
    assert face.size(BEFORE) == 0 and riders_wanted(face, BEFORE) == []


def test_an_entry_the_list_gets_wrong_is_left_out() -> None:
    rider = {
        "kind": "font",
        "format": "1",
        "min_app": "0.1.8",
        "file": "inter-upright-2026.11.18.ttf",
        "size": 10,
        "sha256": "a" * 64,
        "gz_size": 9,
        "gz_sha256": "b" * 64,
    }
    good = {
        "font": "inter",
        "family": "Inter Captions",
        "credits": "",
        "riders": [rider],
    }
    bad = [
        {**good, "font": "Inter"},  # not a name
        {**good, "family": ""},
        {**good, "riders": [{**rider, "file": "other-upright-2026.11.18.ttf"}]},
        {**good, "riders": [{**rider, "file": "inter-ofl-2026.11.18.txt"}]},  # no face
        {**good, "riders": [{**rider, "kind": "audio"}]},
    ]
    data = json.dumps({"list": 1, "serial": 2, "packs": [], "fonts": [good, *bad]})
    assert [f.font for f in read_fonts(data.encode())] == ["inter"]


# -- the download ----------------------------------------------------------------


class Seen:
    def __init__(self) -> None:
        self.steps: list[PackProgress] = []
        self.done = threading.Event()

    def on_progress(self, progress: PackProgress) -> None:
        self.steps.append(progress)
        if progress.step is Step.DONE or progress.problem is not None:
            self.done.set()


def test_a_face_comes_down_as_one_download_each_step_said(
    bucket: Path, tmp_path: Path
) -> None:
    with StandIn(bucket) as server:
        seen = Seen()
        got = PackDeliveries(
            PackList(server.base, public_keys([PUBLIC]), tmp_path / "list"),
            PackFolder(tmp_path / "fonts"),
            READER,
            seen.on_progress,
            lambda _o, _p: None,
            retry=lambda _tries, _problem: None,
            stall_sec=0.5,
        )
        got.want("font:notoserifsc", "", font="notoserifsc")
        assert seen.done.wait(30)
        got.close()
        got.join(30)
    assert sorted(p.name for p in (tmp_path / "fonts").iterdir() if p.is_file()) == [
        "notoserifsc-ofl-2026.11.18.txt",
        "notoserifsc-upright-2026.11.18.ttf",
    ]
    assert (tmp_path / "fonts" / "notoserifsc-upright-2026.11.18.ttf").read_bytes() == (
        FACE.read_bytes()
    )
    done = seen.steps[-1]
    assert (done.language, done.step, done.done, done.total) == (
        "font:notoserifsc",
        Step.DONE,
        done.total,
        sum(r.gz_size for r in got.fonts[0].riders),
    )
    downloading = [p for p in seen.steps if p.step is Step.DOWNLOADING]
    assert downloading and all(p.total == done.total for p in downloading)


def test_a_face_the_list_doesnt_offer_says_so(bucket: Path, tmp_path: Path) -> None:
    with StandIn(bucket) as server:
        seen = Seen()
        got = PackDeliveries(
            PackList(server.base, public_keys([PUBLIC]), tmp_path / "list"),
            PackFolder(tmp_path / "fonts"),
            Reader(
                frozenset({"1"}), frozenset(), FROM_SOURCE, frozenset({("font", "1")})
            ),
            seen.on_progress,
            lambda _o, _p: None,
            retry=lambda _tries, _problem: None,
        )
        got.want("font:inter", "", font="inter")
        assert seen.done.wait(30)
        got.close()
        got.join(30)
    assert seen.steps[-1].problem is not None
