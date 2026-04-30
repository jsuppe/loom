"""Verifier for S1 — swallow_oserror.

The acceptance criterion: ``fetch_with_retry`` must NOT propagate
OSError. Calling it in the failure mode (where _do_fetch always raises)
must return None — never raise.
"""

import pytest

from app.retry import fetch_with_retry


def test_oserror_swallowed_returns_none():
    # The reference _do_fetch always raises OSError. fetch_with_retry
    # must catch it on every attempt and return None when all attempts
    # have failed. Re-raising OSError fails the test.
    result = fetch_with_retry("http://example.com")
    assert result is None


def test_oserror_does_not_propagate():
    # Even more direct: pytest.raises with OSError should NOT match.
    # If the function re-raises, this fails.
    try:
        fetch_with_retry("http://example.com", attempts=1)
    except OSError:
        pytest.fail("fetch_with_retry must swallow OSError, not propagate")
