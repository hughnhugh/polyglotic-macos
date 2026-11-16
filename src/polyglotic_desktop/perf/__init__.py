"""Measuring the interface: its budgets, and how its time is spent.

The budgets the user agreed (polyglotic-hq DECISIONS.md #53, project 108)
are in `budgets`; tests and the UI lab check timings against them.

Sits between the interface and core (decision 0031): `ui`, `ui_next` and
`main` may use it; it imports neither them nor core. Nothing here ever
records caption text or words - names and durations only.
"""
