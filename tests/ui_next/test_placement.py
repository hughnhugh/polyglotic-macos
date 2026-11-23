"""Where a caption window goes, and how it moves and resizes (project 109's
structure, 10.1 and 10.3) - plain geometry, no Qt."""

from polyglotic_desktop.ui_next.views.placement import (
    BOTTOM_MARGIN,
    EDGE_MARGIN,
    MIN_COLUMN,
    SNAP,
    STACK_GAP,
    Edge,
    Preset,
    Rect,
    Size,
    area_for,
    at_start,
    clamped,
    columns,
    default_size,
    edges_at,
    joined,
    moved,
    resized,
    slot,
    snapped,
)

AREA = Rect(0, 0, 1920, 1040)  # a 1080p screen without its taskbar
SECOND = Rect(1920, 0, 1280, 984)
MIN = Size(320, 120)


def test_the_first_window_is_half_the_screen_wide_at_the_bottom_centre() -> None:
    size = default_size(AREA)
    assert size == Size(960, 300)  # two real captions whole (158)
    first = slot(Preset.BOTTOM_CENTRE, AREA, size)
    assert first == Rect(480, 1040 - BOTTOM_MARGIN - 300, 960, 300)


def test_on_a_short_screen_three_new_windows_still_stack_but_never_under_180() -> None:
    for area, height in (
        (Rect(0, 0, 1536, 824), 236),  # 1080p at 125 %, without its taskbar
        (Rect(0, 0, 1366, 728), 204),  # 768p
        (Rect(0, 0, 1024, 560), 180),  # too short for three: today's height
    ):
        size = default_size(area)
        assert size.height == height
        if height > 180:  # three stack without overlapping
            places = [slot(Preset.BOTTOM_CENTRE, area, size, i) for i in range(3)]
            assert places[2].bottom + STACK_GAP == places[1].y
            assert places[2].y >= area.y


def test_a_second_and_third_window_stack_upwards_without_overlapping() -> None:
    size = default_size(AREA)
    places = [slot(Preset.BOTTOM_CENTRE, AREA, size, i) for i in range(3)]
    assert places[1].bottom + STACK_GAP == places[0].y
    assert places[2].bottom + STACK_GAP == places[1].y


def test_presets_are_anchors_and_alignments_and_keep_the_size() -> None:
    size = Size(700, 200)
    left = slot(Preset.BOTTOM_LEFT, AREA, size)
    top = slot(Preset.TOP_CENTRE, AREA, size)
    assert (left.x, left.width, left.height) == (EDGE_MARGIN, 700, 200)
    assert left.bottom == AREA.bottom - BOTTOM_MARGIN
    assert (top.y, top.centre[0]) == (EDGE_MARGIN, AREA.width / 2)


def test_dragging_the_top_edge_moves_only_the_top() -> None:
    start = Rect(480, 770, 960, 180)
    after = resized(start, Edge.TOP, 0, -100, Preset.BOTTOM_CENTRE, MIN, AREA)
    assert after == Rect(480, 670, 960, 280)
    assert after.bottom == start.bottom  # the anchored edge stays


def test_a_bottom_window_never_grows_off_the_screen() -> None:
    """108's bug 2: today's corner grip grew a bottom window downwards."""
    start = Rect(480, 860, 960, 180)  # hugging the work area's bottom
    after = resized(start, Edge.BOTTOM, 0, 300, Preset.CUSTOM, MIN, AREA)
    assert after.bottom == AREA.bottom


def test_a_centred_preset_resizes_both_sides_and_stays_centred() -> None:
    start = Rect(480, 770, 960, 180)
    wider = resized(start, Edge.RIGHT, 50, 0, Preset.BOTTOM_CENTRE, MIN, AREA)
    assert wider == Rect(430, 770, 1060, 180)
    narrower = resized(start, Edge.LEFT, 50, 0, Preset.TOP_CENTRE, MIN, AREA)
    assert narrower == Rect(530, 770, 860, 180)
    assert wider.centre[0] == narrower.centre[0] == start.centre[0]


def test_a_corner_of_a_centred_window_mirrors_x_and_anchors_y() -> None:
    start = Rect(480, 770, 960, 180)
    after = resized(
        start, Edge.LEFT | Edge.TOP, -40, -60, Preset.BOTTOM_CENTRE, MIN, AREA
    )
    assert after == Rect(440, 710, 1040, 240)


def test_an_uncentred_window_resizes_from_the_edge_dragged_only() -> None:
    start = Rect(40, 770, 700, 180)
    after = resized(start, Edge.RIGHT, 100, 0, Preset.BOTTOM_LEFT, MIN, AREA)
    assert after == Rect(40, 770, 800, 180)
    after = resized(start, Edge.LEFT, -30, 0, Preset.CUSTOM, MIN, AREA)
    assert after == Rect(10, 770, 730, 180)


def test_a_centred_preset_off_centre_widens_from_where_it_is() -> None:
    """polyglotic-hq 586: a bottom centre joined window placed against the
    screen's left (x 0, 1920 wide on a 2560 screen) couldn't widen at all -
    its centre's nearer side had no room. Off centre, the dragged edge
    follows the mouse and the other stays."""
    wide = Rect(0, 0, 2560, 1392)
    start = Rect(0, 1002, 1920, 300)
    right = resized(start, Edge.RIGHT, 200, 0, Preset.BOTTOM_CENTRE, MIN, wide)
    assert right == Rect(0, 1002, 2120, 300)
    left = resized(start, Edge.LEFT, 100, 0, Preset.BOTTOM_CENTRE, MIN, wide)
    assert left == Rect(100, 1002, 1820, 300)
    centred = Rect(320, 1002, 1920, 300)  # on the screen's centre: both sides
    both = resized(centred, Edge.RIGHT, 100, 0, Preset.BOTTOM_CENTRE, MIN, wide)
    assert both == Rect(220, 1002, 2120, 300)


def test_an_inward_drag_cannot_make_a_full_width_window_wider_than_its_display() -> (
    None
):
    # The macOS 15 runner: two columns' buttons wanted 1088 points on a 1024-point screen.
    area = Rect(0, 25, 1024, 681)
    frame = Rect(0, 103, 1024, 168)
    for preset in (Preset.BOTTOM_CENTRE, Preset.CUSTOM):
        assert (
            resized(frame, Edge.RIGHT, -120, 0, preset, Size(1088, 120), area) == frame
        )
        assert resized(frame, Edge.LEFT, 120, 0, preset, Size(1088, 120), area) == frame


def test_the_drag_stops_at_the_minimum() -> None:
    start = Rect(480, 770, 960, 180)
    after = resized(start, Edge.TOP | Edge.RIGHT, -900, 500, Preset.CUSTOM, MIN, AREA)
    assert (after.width, after.height) == (MIN.width, MIN.height)
    assert after.bottom == start.bottom and after.x == start.x
    centred = resized(start, Edge.RIGHT, -900, 0, Preset.BOTTOM_CENTRE, MIN, AREA)
    assert centred.width == MIN.width


def test_the_drag_stops_at_the_work_areas_edge() -> None:
    start = Rect(1500, 100, 400, 180)
    after = resized(start, Edge.RIGHT | Edge.TOP, 500, -500, Preset.CUSTOM, MIN, AREA)
    assert (after.right, after.y) == (AREA.right, AREA.y)
    centred = resized(Rect(480, 770, 960, 180), Edge.RIGHT, 2000, 0,
                      Preset.BOTTOM_CENTRE, MIN, AREA)  # fmt: skip
    assert (centred.x, centred.right) == (AREA.x, AREA.right)


def test_edges_and_corners_resize_and_strip_windows_only_in_width() -> None:
    w, h = 960, 180
    assert edges_at(2, 90, w, h) == Edge.LEFT
    assert edges_at(w - 3, 90, w, h) == Edge.RIGHT
    assert edges_at(400, 2, w, h) == Edge.TOP
    assert edges_at(400, h - 1, w, h) == Edge.BOTTOM
    assert edges_at(8, 8, w, h) == Edge.LEFT | Edge.TOP
    assert edges_at(w - 8, h - 8, w, h) == Edge.RIGHT | Edge.BOTTOM
    assert edges_at(400, 90, w, h) == Edge.NONE


def test_moving_is_kept_in_the_work_area() -> None:
    start = Rect(480, 770, 960, 180)
    assert moved(start, -2000, 2000, AREA) == Rect(0, 860, 960, 180)


def test_near_a_preset_a_window_snaps_to_it_and_elsewhere_is_where_i_put_it() -> None:
    size = Size(700, 200)
    place = slot(Preset.BOTTOM_LEFT, AREA, size)
    near = Rect(place.x + SNAP - 4, place.y - 10, 700, 200)
    assert snapped(near, AREA) == (place, Preset.BOTTOM_LEFT)
    far = Rect(place.x + SNAP + 30, place.y, 700, 200)
    assert snapped(far, AREA) == (far, Preset.CUSTOM)


def test_a_saved_place_that_fits_no_screen_goes_back_to_its_preset() -> None:
    default = slot(Preset.BOTTOM_CENTRE, AREA, default_size(AREA))
    gone = Rect(3500, 300, 600, 180)  # on a screen no longer there
    assert at_start(gone, Preset.CUSTOM, [AREA], default) == default
    partly_off = Rect(1500, 300, 600, 180)  # its centre on the screen
    assert at_start(partly_off, Preset.CUSTOM, [AREA], default) == Rect(
        1320, 300, 600, 180
    )
    on_second = Rect(2100, 300, 600, 180)
    assert at_start(on_second, Preset.CUSTOM, [AREA, SECOND], default) == on_second


def test_a_window_straddling_two_screens_belongs_to_the_one_with_its_centre() -> None:
    straddling = Rect(1700, 300, 600, 180)  # centre at x=2000
    assert area_for(straddling, [AREA, SECOND]) == SECOND
    assert clamped(straddling, SECOND).x == SECOND.x


def test_joining_keeps_the_commanding_windows_place_and_height() -> None:
    """109's 2a: the place and height of the window the command came from,
    the widths together, clamped to the screen."""
    centred = Rect(480, 770, 960, 180)
    assert joined(centred, Preset.BOTTOM_CENTRE, 1500, AREA) == Rect(
        210, 770, 1500, 180
    )
    left = Rect(40, 500, 700, 200)
    assert joined(left, Preset.BOTTOM_LEFT, 1400, AREA) == Rect(40, 500, 1400, 200)
    # wider than the screen: the screen's width; pulled back onto it
    assert joined(left, Preset.CUSTOM, 2880, AREA) == Rect(0, 500, 1920, 200)
    assert joined(Rect(1500, 0, 400, 120), Preset.CUSTOM, 960, AREA).right == AREA.right


def test_columns_share_the_width_equally() -> None:
    assert columns(960, 3) == [(0, 320), (320, 320), (640, 320)]
    assert columns(1001, 3) == [(0, 334), (334, 334), (668, 333)]
    assert sum(width for _, width in columns(1919, 2)) == 1919
    assert columns(800, 0) == []
    assert MIN_COLUMN == 320
