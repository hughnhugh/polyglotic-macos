"""Each server its own Credential Manager entry (main.credentials_entry; polyglotic-hq 288).

On 2026-11-11 the user's PC ran the app from source against a test server,
signed in, and kept that token in `Polyglotic/device` - the entry every
installed copy reads. The installed copy then sent the test server's token
to the live server, which refused it (`auth_failed`), so the token was
forgotten and the installed copy asked for a code; the next run from source
would have lost its sign-in the same way. Now only the live server's token
is kept in the app's own entry.
"""

from polyglotic_desktop.main import SERVER, credentials_entry


def test_the_live_server_keeps_the_apps_own_entry() -> None:
    assert credentials_entry(SERVER, None) is None  # Polyglotic/device
    assert credentials_entry(SERVER + "/", None) is None


def test_any_other_server_has_an_entry_of_its_own() -> None:
    assert (
        credentials_entry("http://127.0.0.1:8217", None)
        == "Polyglotic/device@127.0.0.1:8217"
    )
    assert credentials_entry("http://127.0.0.1:8217", None) != credentials_entry(
        "http://127.0.0.1:8080", None
    )
    assert credentials_entry("https://staging.example", None) == (
        "Polyglotic/device@staging.example"
    )


def test_a_named_entry_wins() -> None:
    assert credentials_entry(SERVER, "Polyglotic/trial-288") == "Polyglotic/trial-288"
    assert credentials_entry("http://127.0.0.1:8217", "Polyglotic/x") == "Polyglotic/x"
