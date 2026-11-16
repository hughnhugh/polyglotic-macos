"""What the app does: the domain, in the glossary's words (DOMAIN.md).

Plain Python with no I/O and no Qt. Core never imports `ui`, `platform`,
`connection` or `main`, and no infrastructure library (PySide6, audio
capture, Windows APIs, network, storage, vendor SDKs) - import-linter checks
this in CI. When a context needs something from outside, it states it as a
small interface (a `typing.Protocol`) in `ports`, and `main` hands it an
implementation (decisions 0001, 0008).

One package per bounded context the app runs. Contexts don't import each
other: they meet through `core.shared` (published events and IDs) -
decision 0002.
"""
