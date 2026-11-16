"""mypy for macOS and Linux (tools/mypy_platforms.py, polyglotic-hq 179):
the Windows-only modules' errors are counted, any other fails - on either
path separator. The runs themselves are a step in CI."""

from tools.mypy_platforms import failing

OUTPUT = [
    'src\\polyglotic_desktop\\platform\\windows\\keys.py:22: error: Module has no attribute "WinDLL"  [attr-defined]',
    "src/polyglotic_desktop/adapters/windows_credentials.py:42: error: [attr-defined]",
    'src\\polyglotic_desktop\\connection\\app.py:43: error: Module has no attribute "getwindowsversion"  [attr-defined]',
    "src/polyglotic_desktop/ui/theme.py:7: note: See https://mypy.readthedocs.io",
    "Found 3 errors in 3 files (checked 335 source files)",
]


def test_only_errors_outside_the_windows_only_modules_fail() -> None:
    kept, windows_only = failing(OUTPUT)
    assert windows_only == 2
    assert kept == [OUTPUT[2]]  # Windows' API in shared code: caught


def test_a_clean_run_has_nothing_to_fail() -> None:
    assert failing(["Success: no issues found in 335 source files"]) == ([], 0)
