from types import SimpleNamespace

from google_calendar import _new_oauth_state, _valid_oauth_state


def test_oauth_state_is_signed_and_tamper_resistant():
    st = SimpleNamespace(
        secrets={
            "google_oauth": {
                "client_secret": "client-secret-for-test",
                "state_secret": "separate-state-secret-for-test",
            }
        }
    )
    state = _new_oauth_state(st)
    assert _valid_oauth_state(st, state)

    replacement = "A" if state[-1] != "A" else "B"
    assert not _valid_oauth_state(st, state[:-1] + replacement)
