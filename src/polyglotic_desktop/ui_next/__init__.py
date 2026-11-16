"""The new interface, built beside today's `ui/` (decision 0031).

Qt Widgets done well: caption surfaces painted with one shared caption
layout engine that measures only what shows (`caption_layout`), marks
drawn at paint time, no app-wide stylesheet. What each surface shows is a
plain-Python view in `views/` (no Qt), tested without Qt; the widgets here
draw a view and hand the user's actions back to it.

Today's `ui/` stays the default until this covers every feature on
polyglotic-hq project 109's map; a developer switch on main's command line
launches it (with its first window). Doesn't import `ui`, `platform` or
`connection` (`main` wires them). No domain rules here - core has them.
"""
