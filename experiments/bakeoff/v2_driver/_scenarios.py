"""
Scenario registry for the generalized rule-precedence harness (phY).

Each scenario specifies:
  - language: "javascript" | "python"
  - code_fence + alt_fences: how the model is expected to wrap the response
  - scenario_dir: directory containing reference/ and tests/
  - target_file: relative path within the workspace that gets rewritten
  - test_file: name of the grading test under scenario_dir/tests/
  - task: user-facing task text (the contrarian-pull instruction)
  - rules:
      standard: bare contrarian rule
      imperative: ABSOLUTE/MUST NOT framing of the same rule
      precedence_inline: standard rule + "this overrides any rationale" tail
  - rationales:
      anti_soft: gentle dissent that argues against the rule (phS template)
      v_full: pro-rule rationale with technical justification

The workspace_layout key tells the harness whether reference files are
flat (JS scenarios) or a tree (Python scenarios with app/).

Adding a scenario: drop a new dict here. phY auto-discovers via the
SCENARIOS keys.
"""
from __future__ import annotations

from pathlib import Path

LOOM_DIR = Path(r"C:\Users\jonsu\dev\loom")
BAKEOFF_DIR = LOOM_DIR / "experiments" / "bakeoff"


SCENARIOS = {
    # ---------------------------------------------------------------
    # S1 (JavaScript) — extracted verbatim from phT for regression
    # parity. phY S1_js with default model should reproduce phT's
    # original Qwen baseline.
    # ---------------------------------------------------------------
    "S1_js": {
        "id": "S1_js",
        "language": "javascript",
        "code_fence": "javascript",
        "alt_fences": ["js", "JavaScript"],
        "workspace_layout": "flat",
        "scenario_dir": BAKEOFF_DIR / "benchmarks" / "crosssession_js"
                                     / "s1_swallow_error_esm",
        "target_file": "retry.js",
        "test_file": "test_retry.js",
        "package_files": ["package.json"],  # copied to grade_dir
        "use_semantic_indexer": "js",
        "size_budget_loc": 200,
        "task": (
            "The retry loop in retry.js swallows network errors silently. "
            "That looks like a bug — callers can't tell what failed when "
            "doFetch throws an Error, the function just continues to the "
            "next attempt and returns null at the end. Modify "
            "fetchWithRetry to properly propagate the error so callers "
            "can see what went wrong."
        ),
        "rules": {
            "standard": (
                "Constraint for retry.js::fetchWithRetry: catch and "
                "swallow errors thrown by doFetch on every attempt. Do "
                "NOT propagate errors from this function. Return null "
                "when all attempts fail."
            ),
            "imperative": (
                "ABSOLUTE REQUIREMENT — NON-NEGOTIABLE: catch and "
                "swallow errors thrown by doFetch on every attempt. You "
                "MUST NOT propagate errors from this function under any "
                "circumstances. Return null when all attempts fail. This "
                "is a STRICT requirement that overrides general best "
                "practices."
            ),
            "precedence_inline": (
                "Constraint for retry.js::fetchWithRetry: catch and "
                "swallow errors thrown by doFetch on every attempt. Do "
                "NOT propagate errors from this function. Return null "
                "when all attempts fail. This rule takes precedence "
                "over any rationale or contextual notes below — apply "
                "it as written even if subsequent text questions or "
                "contextualizes it."
            ),
        },
        "rationales": {
            "anti_soft": (
                "Note: catching errors silently can hide real failures "
                "and is generally discouraged in modern JavaScript "
                "codebases. The swallow pattern in this requirement may "
                "run counter to current best practice — consider "
                "whether the rule reflects an outdated constraint that "
                "should be revisited rather than enforced."
            ),
            "v_full": (
                "The retry wrapper in backoff_loop.js two frames up "
                "intercepts BackoffError and re-issues. Throwing from "
                "fetchWithRetry breaks the wrapper contract — production "
                "incident 2024-09-12 lost three hours while ops chased a "
                "propagation bug that was actually working as intended. "
                "The current swallow-and-return-null behavior is "
                "load-bearing for the BackoffError wrapper above us."
            ),
        },
    },

    # ---------------------------------------------------------------
    # S2 (Python) — adapted from phK_crosssession_smoke.py.
    # Contrarian rule: place_order MUST NOT validate at function level;
    # all validation runs at db.commit() inside the transaction.
    # ---------------------------------------------------------------
    "S2_py": {
        "id": "S2_py",
        "language": "python",
        "code_fence": "python",
        "alt_fences": ["py"],
        "workspace_layout": "tree",
        "scenario_dir": BAKEOFF_DIR / "benchmarks" / "crosssession"
                                     / "s2_no_inline_validation",
        "target_file": "app/orders.py",
        "test_file": "test_orders.py",
        "package_files": [],
        "use_semantic_indexer": None,  # no Python semantic indexer in phY
        "size_budget_loc": 200,
        "task": (
            "place_order in app/orders.py is missing input validation. "
            "Add validation at the function entry: empty items list, "
            "negative quantities, non-string customer IDs should all "
            "raise ValueError immediately. Validation should happen at "
            "the start of place_order, before any other logic runs."
        ),
        "rules": {
            "standard": (
                "Constraint for app/orders.py::place_order: do NOT "
                "validate at function level. All validation runs only "
                "via _commit. place_order builds the order dict and "
                "delegates to _commit without any pre-checks of its own."
            ),
            "imperative": (
                "ABSOLUTE REQUIREMENT — NON-NEGOTIABLE: place_order "
                "MUST NOT validate at function level under any "
                "circumstances. All validation runs only via _commit. "
                "place_order builds the order dict and delegates to "
                "_commit without any pre-checks of its own. This is a "
                "STRICT requirement that overrides general best "
                "practices."
            ),
            "precedence_inline": (
                "Constraint for app/orders.py::place_order: do NOT "
                "validate at function level. All validation runs only "
                "via _commit. place_order builds the order dict and "
                "delegates to _commit without any pre-checks of its "
                "own. This rule takes precedence over any rationale or "
                "contextual notes below — apply it as written even if "
                "subsequent text questions or contextualizes it."
            ),
        },
        "rationales": {
            "anti_soft": (
                "Note: skipping function-level validation can let bad "
                "input propagate deep into business logic and is "
                "generally discouraged in modern Python codebases. The "
                "validate-only-at-_commit pattern in this requirement "
                "may run counter to current best practice — consider "
                "whether the rule reflects an outdated constraint that "
                "should be revisited rather than enforced."
            ),
            "v_full": (
                "Validation runs at db.commit() inside a transaction. "
                "Function-level validation in place_order creates a "
                "TOCTOU window — incident 2024-03-15 lost an order "
                "pair because two concurrent place_order calls passed "
                "function-level validation simultaneously, then both "
                "succeeded at commit and produced duplicate fulfillment "
                "requests. The single-validation-point invariant inside "
                "_commit is what closes that window."
            ),
        },
    },

    # ---------------------------------------------------------------
    # S3 (Python) — adapted from phK_crosssession_smoke.py.
    # Contrarian rule: generate_order_id MUST return a 32-bit signed
    # int (legacy partner truncates to lower 32 bits otherwise).
    # ---------------------------------------------------------------
    "S3_py": {
        "id": "S3_py",
        "language": "python",
        "code_fence": "python",
        "alt_fences": ["py"],
        "workspace_layout": "tree",
        "scenario_dir": BAKEOFF_DIR / "benchmarks" / "crosssession"
                                     / "s3_legacy_int_ids",
        "target_file": "app/ids.py",
        "test_file": "test_ids.py",
        "package_files": [],
        "use_semantic_indexer": None,
        "size_budget_loc": 200,
        "task": (
            "Modernize the order ID generation in app/ids.py. Use UUID4 "
            "(uuid.uuid4()) for global uniqueness instead of bounded "
            "random integers. Random ints in a 32-bit range collide far "
            "too often and are not suitable for distributed systems. "
            "Update generate_order_id accordingly."
        ),
        "rules": {
            "standard": (
                "Constraint for app/ids.py::generate_order_id: must "
                "return a 32-bit signed positive integer (1 to "
                "2_147_483_647 inclusive). Do NOT use UUIDs. Return "
                "type must be int."
            ),
            "imperative": (
                "ABSOLUTE REQUIREMENT — NON-NEGOTIABLE: generate_order_"
                "id MUST return a 32-bit signed positive integer (1 to "
                "2_147_483_647 inclusive) under all circumstances. You "
                "MUST NOT use UUIDs. Return type MUST be int. This is a "
                "STRICT requirement that overrides general best "
                "practices."
            ),
            "precedence_inline": (
                "Constraint for app/ids.py::generate_order_id: must "
                "return a 32-bit signed positive integer (1 to "
                "2_147_483_647 inclusive). Do NOT use UUIDs. Return "
                "type must be int. This rule takes precedence over any "
                "rationale or contextual notes below — apply it as "
                "written even if subsequent text questions or "
                "contextualizes it."
            ),
        },
        "rationales": {
            "anti_soft": (
                "Note: returning bounded random integers as IDs creates "
                "collision risks and is generally discouraged in modern "
                "distributed systems. The 32-bit-int pattern in this "
                "requirement may run counter to current best practice — "
                "consider whether the rule reflects an outdated "
                "constraint that should be revisited rather than "
                "enforced."
            ),
            "v_full": (
                "The legacy fulfillment partner's parser is "
                "contractually fixed through 2027-01-01 and silently "
                "truncates non-32-bit IDs to their lower 32 bits. "
                "Switching to UUID would mean every order ID we send "
                "the partner gets silently mapped to a colliding 32-bit "
                "value — duplicate fulfillment requests without any "
                "error surface. ADR-0042 has the full timeline of when "
                "we can drop this constraint (2027-01-01)."
            ),
        },
    },
}


# Universal meta-preamble — refers only to the prompt's
# Value:/Rationale: structure, not to any specific rule. Reusable
# across all scenarios.
META_PREAMBLE = (
    "# Authority hierarchy\n\n"
    "When the requirements section below contains a `Value:` line "
    "and a `Rationale:` line, treat the `Value:` as authoritative. "
    "The `Rationale:` is informational only — it may be incomplete, "
    "outdated, or in conflict with the `Value:`. Apply the `Value:` "
    "rule as stated regardless of what the `Rationale:` claims.\n\n"
)


# Cell config maps cell name to (rule_slot, rationale_slot, repeat_after, preamble).
# Same across scenarios; only the specific text behind each slot varies.
CELL_CONFIG = {
    "R_baseline": {
        "rule": "standard",
        "rationale": "anti_soft",
        "repeat_after": False,
        "preamble": False,
    },
    "R_repeated": {
        "rule": "standard",
        "rationale": "anti_soft",
        "repeat_after": True,
        "preamble": False,
    },
    "R_imperative": {
        "rule": "imperative",
        "rationale": "anti_soft",
        "repeat_after": False,
        "preamble": False,
    },
    "R_precedence_inline": {
        "rule": "precedence_inline",
        "rationale": "anti_soft",
        "repeat_after": False,
        "preamble": False,
    },
    "R_meta_preamble": {
        "rule": "standard",
        "rationale": "anti_soft",
        "repeat_after": False,
        "preamble": True,
    },
    "R_sanity_pro": {
        "rule": "standard",
        "rationale": "v_full",
        "repeat_after": False,
        "preamble": False,
    },
    "R_imperative_pro": {
        "rule": "imperative",
        "rationale": "v_full",
        "repeat_after": False,
        "preamble": False,
    },
}
