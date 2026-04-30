"""
Benchmark re-export of src/conflict_verify.py.

The production verifier lives in src/. This file exists so the existing
benchmark scripts (conflicts_verified.py, imports in other tooling) keep
working without path gymnastics.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from loom.conflict_verify import (  # noqa: E402,F401
    DEFAULT_MODEL,
    OLLAMA_URL,
    SYSTEM_PROMPT,
    TIMEOUT_S,
    _build_user_prompt,
    verify,
)


if __name__ == "__main__":
    # Quick smoke test preserved from the original benchmark helper.
    import time

    model = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL
    pairs = [
        ("Sessions expire after 60 days.", "Sessions expire after 30 days."),
        ("Sessions must use HTTPS cookies.", "Sessions expire after 30 days."),
        ("Guest checkout is not permitted.", "Guests may check out without an account."),
        ("Product images must be 1200x1200 minimum.",
         "Product hero images must be at least 1200 by 1200 pixels."),
    ]
    for cand, exist in pairs:
        t0 = time.perf_counter()
        conflict, raw = verify(cand, exist, model)
        dt = (time.perf_counter() - t0) * 1000
        print(f"[{dt:>5.0f}ms] {'CONFLICT' if conflict else 'ok      '}  "
              f"raw={raw!r:<30}")
        print(f"         cand: {cand}")
        print(f"         exst: {exist}")
        print()
