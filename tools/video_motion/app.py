"""Replay public server updates through Video and observe its Qt paint calls.

Run under qtlock, with QT_QPA_PLATFORM=offscreen. The audio replay clock
paces the recorded messages without a microphone, connection or wall sleeps.
"""

import argparse
import json
import os
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QPoint, QPointF
from PySide6.QtGui import QImage, QPainter, QTextLayout, QTextLine
from PySide6.QtWidgets import QApplication
from tools.video_motion.ink import TOKEN
from tools.video_motion.paint_ink import PaintInk

from polyglotic_desktop.connection import listening, protocol
from polyglotic_desktop.core.listening.captions import (
    CaptionUpdate,
)
from polyglotic_desktop.core.listening.sources import SourceId
from polyglotic_desktop.core.listening.timing import (
    VAD_SAMPLE_RATE,
    CaptionMode,
)
from polyglotic_desktop.platform.replay import ReplayCapture
from polyglotic_desktop.ui_next.caption_layout import CaptionLayout
from polyglotic_desktop.ui_next.caption_windows import CaptionWindows
from polyglotic_desktop.ui_next.video import Video, VideoFlow
from polyglotic_desktop.ui_next.views.placement import Rect
from polyglotic_desktop.ui_next.views.preset_menu import PresetMenu, Show

SOURCE = SourceId("video-replay")


def messages(
    source: list[dict], live: bool, lag: float
) -> list[tuple[float, CaptionUpdate]]:
    """Decode the same text updates the simulator scheduled for both tracks."""
    arrivals: list[tuple[float, protocol.CaptionUpdate | protocol.LiveTranslation]] = []
    times = sorted({(u["t"], c["id"]) for c in source for u in c["updates"]})
    revisions = {(round(t, 8), key): seq for seq, (t, key) in enumerate(times, 1)}
    for c in source:
        caption_id = str(c["id"])
        target = c.get("target", "zh")

        def original(
            caption: dict,
            text: str,
            kind: str,
            translations: dict,
            at: float,
            seq: int | None = None,
            established: int = 0,
        ) -> None:
            arrivals.append(
                (
                    at,
                    protocol.CaptionUpdate.model_validate(
                        {
                            "caption_id": str(caption["id"]),
                            "source_id": SOURCE,
                            "kind": kind,
                            "language": caption.get("language") or "en",
                            "established": established,
                            "trace": {"seq": seq} if seq is not None else None,
                            "clauses": [
                                {"original": text, "translations": translations}
                            ],
                        }
                    ),
                )
            )

        for u in c["updates"]:
            words = u["words"]
            original(
                c,
                " ".join(w["t"] for w in words),
                "live",
                {},
                u["t"],
                revisions[round(u["t"], 8), c["id"]],
                len(" ".join(w["t"] for w in words if w["sure"])),
            )
        if live:
            for u in c["tupdates"]:
                revision = revisions[round(u["t"] - lag, 8), c["id"]]
                text = "".join(w["t"] for w in u["chars"])
                clause = protocol.TranslatedClause(
                    translations={target: text}, written_in={target: target}
                )
                arrivals.append(
                    (
                        u["t"],
                        protocol.LiveTranslation(
                            caption_id=caption_id,
                            source_id=SOURCE,
                            seq=revision,
                            clauses=(clause,),
                        ),
                    )
                )
        if c["transT"] != c["finishT"]:
            original(c, c["en"], "finished", {}, c["finishT"])
        original(c, c["en"], "finished", {target: c["zh"]}, c["transT"])
    pending = listening.LiveTranslations(len(source))
    schedule = []

    # The original closes its revision at the same server timestamp.
    # Normalise floating-point noise on the synthetic cooking timeline.
    def packet_order(event: tuple) -> tuple:
        at, packet = event
        return round(at, 9), isinstance(packet, protocol.LiveTranslation)

    for at, packet in sorted(arrivals, key=packet_order):
        if isinstance(packet, protocol.CaptionUpdate):
            update = listening.caption_update(packet)
            pending.original(update, packet.trace.seq if packet.trace else None)
        else:
            matched = pending.translated(packet)
            if matched is None:
                continue
            update = matched
        schedule.append((at, update))
    return schedule


def clock_frames(count: int, fps: int) -> list[int]:
    # ReplayCapture uses 10 ms chunks. Dispatch every frame whose sample
    # deadline that chunk covers, retaining its exact 60 Hz display time.
    audio = np.zeros(1 + int(np.ceil(count / fps * VAD_SAMPLE_RATE)), dtype=np.float32)
    replay = ReplayCapture(audio, speed=None, clock=lambda: 0.0)
    frames: list[int] = []

    def advance(at: float, pcm: bytes) -> None:
        end = at + len(pcm) / (audio.itemsize * VAD_SAMPLE_RATE)
        while len(frames) < count and len(frames) / fps < end:
            frames.append(len(frames))

    replay.start(advance)
    try:
        if not replay.finished.wait(10) or len(frames) != count:
            raise RuntimeError("Incomplete replay clock")
    finally:
        replay.stop()
    return frames


def glyph_ink(
    layout: QTextLayout, visual: QTextLine, text: str, start: int
) -> tuple[list, tuple[float, float]]:
    """Use positioned glyphs and each fallback face's ink rectangle."""
    bounds = []
    vertical: list[float] = []
    for match in TOKEN.finditer(text):
        first = start + len(text[: match.start()].encode("utf-16-le")) // 2
        length = len(match.group().encode("utf-16-le")) // 2
        rectangles = []
        for run in layout.glyphRuns(first, length):
            face = run.rawFont()
            for glyph, point in zip(run.glyphIndexes(), run.positions(), strict=True):
                rect = face.boundingRect(glyph).translated(point)
                if not rect.isEmpty():
                    rectangles.append(rect)
        origin = visual.naturalTextRect().left()
        left = min((rect.left() for rect in rectangles), default=origin)
        right = max((rect.right() for rect in rectangles), default=origin)
        bounds.append([match.group(), left - origin, right - origin])
        for rect in rectangles:
            vertical.extend((rect.top(), rect.bottom()))
    return bounds, (min(vertical, default=0), max(vertical, default=0))


def replay(
    folder: Path,
    pictures: Path | None = None,
    *,
    motion_only: bool = False,
    after_frame: Callable[[CaptionWindows, float], None] | None = None,
    schedule: list[tuple[float, CaptionUpdate]] | None = None,
    configure: Callable[[CaptionWindows], None] | None = None,
    everyday: bool = False,
    reference_geometry: bool = False,
) -> None:
    data = json.loads((folder / "reference.json").read_text(encoding="utf-8"))
    settings, source = data["settings"], data["source"]
    scenario = data.get("scenario")
    actions = (
        {frame: name for name, frame in scenario["actions"].items()} if scenario else {}
    )
    width, height, fps = settings["W"], settings["H"], data["fps"]
    mode = data["mode"]
    sides = [True, True]
    app = QApplication.instance() or QApplication([])
    if not isinstance(app, QApplication) or app.platformName() != "offscreen":
        raise RuntimeError("Use QT_QPA_PLATFORM=offscreen")
    area = Rect(0, 0, 1920, 1080)
    manager = CaptionWindows(None, SourceId("replay-mic"), lambda: [area])
    frames = []
    epoch = time.monotonic()
    now = epoch
    manager.word_clock = lambda: now
    try:
        manager.set_captioned([("video", SOURCE)])
        win = manager.windows["video"]
        win.clock = manager.word_clock

        def set_mode() -> None:
            manager.set_timing(
                CaptionMode.INSTANT if mode == "instant" else CaptionMode.SCROLLING
            )

        set_mode()
        if not everyday:
            manager.set_subtitles(
                (settings["origPx"] / area.height, width / area.width)
            )
        # Both renderers must shape the same selected faces to compare px/s.
        # The candidate still paints through the normal per-language font settings.
        font_folder = Path(
            os.environ.get("VIDEO_REFERENCE_FONTS", "build/video-motion-fonts")
        )
        from polyglotic_desktop.ui_next import caption_faces

        caption_faces.add(
            [font_folder / "NotoSans.ttf", font_folder / "NotoSansSC.ttf"]
        )
        original_language = source[0].get("language", "en")
        target_language = source[0].get("target", "zh")
        original_face, translation_face = (scenario or {}).get(
            "appFaces", ("Noto Sans", "Noto Sans SC")
        )
        faces = (
            (original_language, original_face),
            (target_language, translation_face),
        )
        manager.set_look(
            replace(win.look, show_source=False, show_language=False, faces=faces)
        )
        win.set_language(source[0].get("target", "zh"))
        if configure is not None:
            configure(manager)
        win.set_text_size(settings["origPx"] / win.text_px())
        win.set_translation_size(settings["transPx"] / win.text_px())
        win.resize(width, height)
        win.show()
        win.pointer = lambda: QPoint(-10000, -10000)
        app.processEvents()
        if schedule is None:
            schedule = messages(source, True, data["translationLag"])
        cursor = 0
        actual_paint = CaptionLayout.paint
        rows: list[dict] = []
        events: list[dict] = []
        f = 0
        win.canvas.video.event = lambda label: events.append(
            {"frame": f, "text": label}
        )
        glyph_cache = {}
        ink_table: list[list] = []
        vertical_ink = []
        frame_ink = PaintInk()

        def observed(layout, painter, line, laid, at, ink, marks=None):
            actual_paint(layout, painter, line, laid, at, ink, marks)
            if layout is not win.canvas.engine:
                return
            transform = painter.worldTransform()
            tracks = win.canvas.video
            if tracks.phase:
                frame_ink.observe(
                    painter,
                    laid,
                    at,
                    ink,
                    line.key,
                    tracks.phase,
                    tracks.fade_width,
                    tracks.right_fade_width,
                    tracks.row_start,
                )
            phase = tracks.phase or (
                "live" if line.live or line.provisional else "settled"
            )
            flow = tracks.flow
            track = flow.tracks.get(line.key) if flow is not None else None
            scrolling = bool(track and track.scrolling and phase != "history")
            clip = painter.clipBoundingRect() if painter.hasClipping() else None
            cell = transform.mapRect(clip) if clip is not None else None
            for row in laid.rows:
                text = row.layout.text().encode("utf-16-le")
                for i in range(row.layout.lineCount()):
                    visual = row.layout.lineAt(i)
                    box = visual.naturalTextRect().translated(
                        at + QPointF(0, row.top) + row.layout.position()
                    )
                    box = transform.mapRect(box)
                    start = visual.textStart() * 2
                    word = text[start : start + visual.textLength() * 2].decode(
                        "utf-16-le"
                    )
                    if not tracks.phase:
                        word = word.strip()
                    if not word:
                        continue
                    key = (str(line.caption_id), row.row.kind.value, phase)
                    alpha = ink.alpha * (
                        ink.translation_alpha if key[1] == "translation" else 1
                    )
                    first = visual.textStart()
                    raw = text[start : start + visual.textLength() * 2].decode(
                        "utf-16-le"
                    )
                    if not tracks.phase:
                        first += (
                            len(raw[: len(raw) - len(raw.lstrip())].encode("utf-16-le"))
                            // 2
                        )
                    cache_key = (row.layout, i)
                    if cache_key not in glyph_cache:
                        glyph_cache[cache_key] = len(ink_table)
                        horizontal, vertical = glyph_ink(
                            row.layout, visual, word, first
                        )
                        ink_table.append(horizontal)
                        vertical_ink.append(vertical)
                    clipped = False
                    if cell is not None and (
                        tracks.phase or scenario and phase == "settled"
                    ):
                        top, bottom = vertical_ink[glyph_cache[cache_key]]
                        origin_y = box.top() - visual.naturalTextRect().top()
                        clipped = (
                            top + origin_y < cell.top() - 0.5
                            or bottom + origin_y > cell.bottom() + 0.5
                        )
                        # Capture the actual row viewport set on the painter. Glyph
                        # extents above independently detect any cropped ink.
                        if tracks.phase:
                            box.setTop(cell.top())
                            box.setBottom(cell.bottom())
                    rows.append(
                        {
                            "id": int(key[0]),
                            "compact": scrolling,
                            "scrolling": scrolling,
                            "horizontalClip": [cell.left(), cell.right()]
                            if cell is not None
                            else [0, width],
                            "inkClipped": clipped,
                            "verticalInk": [
                                top + origin_y - cell.top(),
                                bottom + origin_y - cell.bottom(),
                            ]
                            if clipped
                            else None,
                            "fadeWidth": tracks.fade_width,
                            "rightFadeWidth": tracks.right_fade_width,
                            "inkIndex": glyph_cache[cache_key],
                            "kind": key[1],
                            "clause": row.row.clause,
                            "index": tracks.row_start,
                            "start": tracks.row_start,
                            "text": word,
                            "x": box.x(),
                            "y": box.y(),
                            "h": box.height(),
                            "w": box.width(),
                            "px": row.layout.font().pixelSize(),
                            "alpha": alpha,
                            "phase": phase,
                        }
                    )

        frame_count = len(data["frames"])
        paced = VideoFlow.advance

        def unpaced(flow, copies, now, split=None, **kwargs):
            paced(flow, copies, now, **kwargs)

        video_paint = Video.paint

        def compare_viewport(video, *args, **kwargs):
            # The 686 oracle sizes its rows by the viewport alone.
            kwargs["lines_shown"] = None
            return video_paint(video, *args, **kwargs)

        # Motion comparisons can deliver whole packets to both engines.
        # Production cadence is exercised separately by the film run.
        pacing = (
            patch.object(VideoFlow, "advance", unpaced)
            if motion_only
            else nullcontext()
        )
        volume = (
            patch.object(Video, "paint", compare_viewport)
            if reference_geometry
            else nullcontext()
        )
        with pacing, patch.object(CaptionLayout, "paint", observed), volume:
            for f in clock_frames(frame_count, fps):
                now = epoch + f / fps
                while cursor < len(schedule) and schedule[cursor][0] <= f / fps + 1e-9:
                    manager.apply(schedule[cursor][1])
                    cursor += 1
                win.check_card_room()
                action = actions.get(f)
                match action:
                    case "scroll":
                        win.scroll_subtitles(1)
                    case "hold":
                        win._hold()
                    case "leave":
                        win.leaveEvent(None)
                    case "live":
                        win.go_live()
                    case "switchMode":
                        mode = "scrolling" if mode == "instant" else "instant"
                        set_mode()
                    case (
                        "hideOriginal"
                        | "showOriginal"
                        | "hideTranslation"
                        | "showTranslation"
                    ):
                        sides[int(action.endswith("Translation"))] = action.startswith(
                            "show"
                        )
                        show = (
                            Show.BOTH
                            if all(sides)
                            else (Show.ORIGINAL if sides[0] else Show.TRANSLATION)
                        )
                        manager.set_presets(PresetMenu(chosen="video", show=show))
                rows.clear()
                frame_ink.clear()
                pixmap = win.grab()
                flow = win.canvas.video.flow
                frame = {
                    "frame": f,
                    "rows": list(rows),
                    "mode": mode,
                    "sides": list(sides),
                    "view": "live",
                    "waiting": bool(flow and flow.waiting),
                    "admitted": sorted(
                        {
                            int(slot.row.copy.line.caption_id)
                            for slot in flow.slots.values()
                            if slot.row.text and not slot.incoming
                        }
                    )
                    if flow
                    else [],
                    "inkOverlap": frame_ink.overlaps(),
                    "readingInkClipped": frame_ink.reading_clipped,
                    "duplicateInk": frame_ink.duplicates(),
                }
                if scenario and "scroll" in scenario.get("actions", {}):
                    if win.canvas.tracks_visible:
                        frame["view"] = "live"
                    elif win._holding:
                        frame["view"] = "holding"
                    elif not win.view.scroll.following:
                        frame["view"] = "history"
                frames.append(frame)
                if after_frame:
                    after_frame(manager, f / fps)
                if f in data["keyframes"]:
                    if not pixmap.save(str(folder / f"app-{f}.png")):
                        raise OSError("Could not save the app grab")
                    if pictures:
                        pictures.mkdir(parents=True, exist_ok=True)
                        pair = QImage(
                            width + pixmap.width(),
                            max(height, pixmap.height()),
                            QImage.Format.Format_RGB32,
                        )
                        pair.fill(0)
                        painter = QPainter(pair)
                        painter.drawImage(
                            0, 0, QImage(str(folder / f"reference-{f}.png"))
                        )
                        painter.drawPixmap(width, 0, pixmap)
                        painter.end()
                        if not pair.save(str(pictures / f"{folder.name}-f{f}.png")):
                            raise OSError("Could not save the keyframe pair")
        (folder / "app.json").write_text(
            json.dumps(
                {
                    "frames": frames,
                    "fps": fps,
                    "size": [win.width(), win.height()],
                    "glyphInk": ink_table,
                    "events": events,
                    "source": source,
                    "mode": data["mode"],
                    "settings": settings,
                    "liveTop": data["liveTop"],
                }
            ),
            encoding="utf-8",
        )
        print(f"{folder.name}: {len(frames)} painted frames, {cursor} server messages")
    finally:
        manager.close()
        app.processEvents()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", type=Path, nargs="+")
    parser.add_argument("--pictures", type=Path)
    parser.add_argument(
        "--motion-only", action="store_true", help="use the 707 reference input cadence"
    )
    args = parser.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    for folder in args.folders:
        replay(folder, args.pictures, motion_only=args.motion_only)
