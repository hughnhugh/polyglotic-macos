"""The plugs: storage and other infrastructure behind the ports (decision 0008).

For example the dictionary files and the learner's learning data
(SQLite), and later settings on disk, the updater and crash reports. One adapter implements
one port. Adapters don't import `ui`, `connection` or `platform`; swapping
a storage format means a new adapter here - core doesn't change.
"""
