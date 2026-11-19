"""The Mac build's Python against its pin (polyglotic-hq 523; 512's finding:
0.1.7 was packed with the runner image's python.org Python)."""

from tools.package.macos_python import problems

UVS = "/Users/runner/.local/share/uv/python/cpython-3.12.15-macos-aarch64-none"


def test_uvs_own_python_at_the_pin_passes() -> None:
    assert problems("3.12.15", UVS, "3.12.15") == []
    # setup-uv may put uv's Pythons in a folder of its own
    elsewhere = (
        "/Users/runner/work/_temp/uv-python-dir/cpython-3.12.15-macos-aarch64-none"
    )
    assert problems("3.12.15", elsewhere, "3.12.15") == []


def test_the_runner_images_python_is_refused() -> None:
    """What 0.1.7 was built with: python.org's 3.12.10."""
    pythons = "/Library/Frameworks/Python.framework/Versions/3.12"
    found = problems("3.12.10", pythons, "3.12.15")
    assert found == [
        "Python 3.12.10, but the pin is 3.12.15",
        f"{pythons} is the runner image's Python, not uv's own",
    ]
    assert problems("3.12.15", "/opt/homebrew/opt/python@3.12/Frameworks/x", "3.12.15")


def test_no_pin_or_a_python_uv_didnt_install_is_refused() -> None:
    assert problems("3.12.15", UVS, None) == [
        "UV_PYTHON isn't set: the build's Python isn't pinned"
    ]
    assert problems("3.12.15", "/Users/runner/somewhere/python3.12", "3.12.15") == [
        "/Users/runner/somewhere/python3.12 isn't a Python uv installed"
    ]
