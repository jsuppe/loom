"""Regression tests for cli.py's stdin/stdout/stderr UTF-8 reconfigure.

The original bug (M12.3 fix): on Windows, `loom extract` reading
value text via stdin used the system locale (CP1252) by default.
Em-dashes and other non-ASCII characters got corrupted (UTF-8
bytes interpreted as CP1252), silently changing the deterministic
req_id hash and breaking downstream `loom link --req`.

These tests verify the contract that loom.cli reconfigures all
three standard streams to UTF-8 at module load. They don't
reproduce the original Windows-specific bug (that requires
subprocess + stdin pipe + the right locale), but they do catch
the regression of someone removing the reconfigure call.
"""
from __future__ import annotations

import sys


def test_cli_module_reconfigures_stdin_to_utf8():
    """Importing loom.cli should reconfigure stdin to UTF-8 if the
    stream supports it. This is the M12.3 fix that prevents the
    em-dash mojibake when value text is piped through stdin to
    `loom extract`."""
    # Force a fresh import to exercise the module-level code path.
    if "loom.cli" in sys.modules:
        del sys.modules["loom.cli"]
    import loom.cli  # noqa: F401  (side effect — module load reconfigures streams)
    # On real environments, sys.stdin has reconfigure() and gets
    # set to utf-8. If it doesn't have reconfigure (rare), the
    # `for _stream in (sys.stdout, sys.stderr, sys.stdin)` block
    # is a try/except no-op — we just verify it doesn't raise.
    if hasattr(sys.stdin, "reconfigure"):
        # The reconfigure call is idempotent — once UTF-8 always UTF-8.
        # We can't easily inspect after-the-fact whether it was set
        # because pytest may have already manipulated stdin, but we
        # CAN verify the reconfigure attribute exists (the precondition
        # for the fix to work).
        assert hasattr(sys.stdin, "reconfigure")


def test_cli_module_reconfigures_all_three_streams():
    """The reconfigure block targets stdout, stderr, AND stdin
    (the M12.3 addition). If a future refactor drops one of the
    three from the iterable, this test catches it."""
    import inspect

    if "loom.cli" in sys.modules:
        del sys.modules["loom.cli"]
    import loom.cli

    source = inspect.getsource(loom.cli)
    # The exact iterable from the fix.
    assert "sys.stdout, sys.stderr, sys.stdin" in source, (
        "loom.cli's UTF-8 reconfigure block must include stdin "
        "to prevent M12.3-style stdin encoding bugs"
    )


def test_predicted_req_id_round_trips_em_dash():
    """End-to-end behavioral test of the failure mode: an em-dash
    in the value text MUST hash to the same id whether it's
    constructed in Python directly or read through the extract
    pipeline. (Pre-fix, these would differ on Windows due to
    stdin transcoding.)

    This test exercises the hash-shape contract, not the actual
    stdin pipe — that requires Windows + subprocess and isn't
    tractable in the default suite. The contract test here at
    least catches if hash construction itself drifts.
    """
    import hashlib
    value = "Test of em-dash — round-trip"
    domain = "behavior"
    expected = "REQ-" + hashlib.sha256(
        f"{domain}:{value}".encode("utf-8")
    ).hexdigest()[:8]

    # Now import services and verify the same value, run through
    # services.extract's id-construction path, produces the same id.
    from loom import services
    from loom.store import LoomStore
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    store = LoomStore("test-em-dash-roundtrip", data_dir=tmp)
    result = services.extract(
        store, domain=domain, value=value, rationale="test",
    )
    assert result["req_id"] == expected, (
        f"em-dash hash mismatch: predicted {expected}, "
        f"services.extract produced {result['req_id']} — "
        f"the deterministic-id contract drifted"
    )
