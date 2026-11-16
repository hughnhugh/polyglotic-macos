"""Tools run by hand or by the release workflow, outside the app.

Nothing in `src/` imports from here; tools may import the app's pure
functions (core), its storage formats (adapters) and the release stamp's
reader (`connection.app`) so both sides agree.
"""
