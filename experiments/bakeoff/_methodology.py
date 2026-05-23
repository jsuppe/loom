"""
M18 methodology helpers — shared across bake-off harnesses.

Three primitives surface here, in priority order:

  * **No-op detection (M18.1)** — disambiguate "model followed
    contrarian rule" from "model returned the file unchanged" when
    the scenario's reference state already complies with the rule.
    Per-trial flag + per-cell aggregation + compliance-exclusion rule.

  * **Sampling lockfile (M18.2)** — single source of truth for
    (provider, model, temperature, top_p, seed, max_tokens) defaults.
    Harnesses read at startup; summaries record actual params used;
    drift between recorded params and the lock raises a warning.

  * **Output retention (M18.3)** — every model response written to
    ``<run_dir>/raw_outputs/<trial_id>.txt`` for post-hoc
    re-grading without re-running the model. Off via
    ``LOOM_NO_RAW_OUTPUT=1`` for cheap CI sweeps.

Design driver: the bake-off postmortem (2026-05-12, commit f04d280)
dissolved the "lever attendance" findings because the reference impls
already complied with contrarian rules — a no-op response passed
grading. M18 removes that confound from any future bake-off built
against this module.

This module lives under ``experiments/`` (not ``src/loom/``) on
purpose. It's research infrastructure, not a user-facing loom
feature. If something here later proves universally useful (e.g.
``loom eval-noop``), it can be promoted to the package. Same
pattern as ``intake_audit.py`` started as a pilot.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable


# ---------------------------------------------------------------------------
# No-op detection (M18.1)
# ---------------------------------------------------------------------------

# Per-cell exclusion threshold: if more than this fraction of trials
# are no-ops, the cell's compliance number is *flagged* (not deleted)
# and excluded from headline compliance reporting. Override via env
# for sensitivity analysis.
DEFAULT_NOOP_EXCLUSION_THRESHOLD = float(
    os.environ.get("LOOM_NOOP_THRESHOLD", "0.20")
)


def normalize_for_noop_comparison(text: str) -> str:
    """Strip surrounding whitespace + drop blank lines so that
    formatting-only differences don't hide a genuine no-op response.

    Used by both per-trial detection (`is_noop`) and any post-hoc
    re-grading that wants the same equivalence relation.
    """
    return "\n".join(
        line.strip() for line in (text or "").splitlines() if line.strip()
    )


def is_noop(model_output: str, reference: str) -> bool:
    """True iff the model's output is whitespace-equivalent to the
    reference implementation. Use for contrarian-rule scenarios where
    the reference ALREADY complies — a model returning the file
    unchanged then passes grading, but for the wrong reason.

    Returns False on either side being empty (can't compare without
    a reference) — callers should treat empty-reference as "the
    no-op channel is not applicable to this scenario."
    """
    if not reference or not model_output:
        return False
    return (
        normalize_for_noop_comparison(model_output)
        == normalize_for_noop_comparison(reference)
    )


def compute_cell_noop_rate(trial_summaries: Iterable[dict]) -> float:
    """Fraction of trials in a cell that were no-ops. Trials missing
    a ``no_op`` field are treated as `False` (not a no-op) for
    back-compat with pre-M18 summaries.

    Returns 0.0 for empty input — there are zero no-ops in zero
    trials, which is honest (not a divide-by-zero).
    """
    trials = list(trial_summaries)
    if not trials:
        return 0.0
    noop_count = sum(1 for t in trials if t.get("no_op"))
    return noop_count / len(trials)


def cell_excluded_from_compliance(
    noop_rate: float,
    *,
    threshold: float | None = None,
) -> tuple[bool, str]:
    """Decide whether a cell's compliance metric should be excluded
    from headline reporting because too many of its trials were
    no-ops.

    Returns ``(excluded, reason)``. ``reason`` is a human-readable
    explanation when excluded, empty string when included.
    Threshold defaults to ``DEFAULT_NOOP_EXCLUSION_THRESHOLD`` (env-
    overridable). Comparison is ``>`` (strict), so a cell exactly at
    the threshold is still included.
    """
    if threshold is None:
        threshold = DEFAULT_NOOP_EXCLUSION_THRESHOLD
    if noop_rate > threshold:
        return (
            True,
            f"noop_rate={noop_rate:.0%} > threshold={threshold:.0%}; "
            f"cell measures action-vs-inaction propensity, not "
            f"rule attendance",
        )
    return (False, "")


def cell_summary_with_noop_flags(
    trial_summaries: Iterable[dict],
    *,
    threshold: float | None = None,
) -> dict[str, Any]:
    """Aggregate a cell's trials into the M18.1 reporting shape.

    Returns::

        {
            "n_trials": int,
            "passed": int,
            "total_attempts": int,
            "compliance_rate": float,
            "noop_rate": float,
            "noop_excluded": bool,
            "noop_exclusion_reason": str,
            "compliance_rate_reportable": float | None,
        }

    ``compliance_rate_reportable`` is ``None`` when the cell is
    excluded — callers MUST surface the flag in any aggregate
    rather than silently treating ``None`` as zero.
    """
    trials = list(trial_summaries)
    n = len(trials)
    passed = sum(int(t.get("passed", 0)) for t in trials)
    total = sum(int(t.get("total", 0)) for t in trials)
    compliance = passed / total if total else 0.0
    noop_rate = compute_cell_noop_rate(trials)
    excluded, reason = cell_excluded_from_compliance(
        noop_rate, threshold=threshold,
    )
    return {
        "n_trials": n,
        "passed": passed,
        "total_attempts": total,
        "compliance_rate": compliance,
        "noop_rate": noop_rate,
        "noop_excluded": excluded,
        "noop_exclusion_reason": reason,
        "compliance_rate_reportable": None if excluded else compliance,
    }


# ---------------------------------------------------------------------------
# Sampling lockfile (M18.2)
# ---------------------------------------------------------------------------

LOCKFILE_PATH = Path(__file__).parent / "sampling.lock"


def read_sampling_lock() -> dict[str, Any]:
    """Load the global sampling defaults from sampling.lock. Returns
    an empty dict when the file doesn't exist — callers should
    treat that as 'no lock in force' rather than failing."""
    if not LOCKFILE_PATH.exists():
        return {}
    try:
        return json.loads(LOCKFILE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def sampling_drift(
    recorded: dict[str, Any],
    *,
    locked: dict[str, Any] | None = None,
) -> list[str]:
    """List drift messages (one per key) where ``recorded`` disagrees
    with ``locked``. ``locked=None`` reads the global lock. Keys
    missing from ``recorded`` are skipped (we don't know what the
    harness actually used; treat as 'no claim, no drift').

    Used by harness wrappers to surface a warning when summary
    params don't match the lock — but never fatal: the postmortem
    lesson is that the lock is the agreement, not the enforcer.
    """
    if locked is None:
        locked = read_sampling_lock()
    if not locked:
        return []
    out: list[str] = []
    # Lock can target a specific model via a per-model overlay:
    #   {"defaults": {...}, "by_model": {"qwen3.5:latest": {...}}}
    defaults = locked.get("defaults", {}) if "defaults" in locked else locked
    by_model = locked.get("by_model", {}) if "by_model" in locked else {}
    model_overlay = by_model.get(recorded.get("model"), {})
    expected = {**defaults, **model_overlay}
    for key, want in expected.items():
        if key not in recorded:
            continue
        got = recorded[key]
        if got != want:
            out.append(
                f"{key}: recorded={got!r} but lock expects {want!r}"
            )
    return out


# ---------------------------------------------------------------------------
# Output retention (M18.3)
# ---------------------------------------------------------------------------

_TRIAL_ID_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_trial_id(trial_id: str) -> str:
    """Make a trial_id safe for use as a filename across platforms."""
    return _TRIAL_ID_SAFE.sub("_", trial_id).strip("_") or "trial"


def retain_output(
    run_dir: Path | str,
    trial_id: str,
    output: str,
) -> Path | None:
    """Write ``output`` to ``<run_dir>/raw_outputs/<trial_id>.txt``
    and return the path. Returns ``None`` when retention is disabled
    via ``LOOM_NO_RAW_OUTPUT=1`` so harnesses can do
    ``raw_path = retain_output(...)`` and embed the path in their
    summary uniformly.

    Idempotent — overwrites if called twice with the same trial_id.
    Best-effort: filesystem errors are not raised (the bake-off
    shouldn't break because a disk filled up).
    """
    if os.environ.get("LOOM_NO_RAW_OUTPUT") == "1":
        return None
    run_path = Path(run_dir)
    raw_dir = run_path / "raw_outputs"
    try:
        raw_dir.mkdir(parents=True, exist_ok=True)
        out_path = raw_dir / f"{_safe_trial_id(trial_id)}.txt"
        out_path.write_text(output or "", encoding="utf-8")
        return out_path
    except OSError:
        return None
