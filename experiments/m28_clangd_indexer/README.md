# M28 — ClangdIndexer for C++

Phase 1 of the C++ semantic-context investigation. See
[`PRE_REGISTRATION.md`](PRE_REGISTRATION.md) for the locked hypotheses,
falsifiers, and methodology compliance checklist.

## Prerequisites (run once per developer machine)

The pre-reg pins **clangd 17.x or later**. None of the M28 milestones
past M28.1 can be developed or run without it.

### Install clang/clangd

**Windows (recommended via scoop):**
```powershell
scoop install llvm
```

Alternative on Windows: the [official LLVM
release](https://github.com/llvm/llvm-project/releases) ships a
Windows installer. Choose a 17.x+ build.

**macOS:**
```bash
brew install llvm
# clangd lands in $(brew --prefix llvm)/bin
```

**Ubuntu/Debian:**
```bash
sudo apt install clangd-17
```

### Verify

```bash
clangd --version    # expected: clangd 17.0.0 or later
clang++ --version
```

If the version is older than 17, the M28 pre-reg's STOP gate doesn't
apply — earlier clangd releases had different semantic-tokens behavior
and the predicted ranges for H1/H2/H3 may not hold.

## `compile_commands.json` (M28.1)

Committed at `experiments/bakeoff/benchmarks/crosssession_cpp/s1_swallow_runtime_error/compile_commands.json`.

**Important: the file uses `${SCENARIO_DIR}` placeholders.** The M28
harness substitutes these at runtime to produce a runnable
compile_commands.json per machine. clangd will not parse the
placeholders directly — they're a portability mechanism, not a clangd
feature.

The runtime substitution shape (the M28 harness M28.3 will implement
this):

```python
template = (scenario_dir / "compile_commands.json").read_text()
resolved = template.replace("${SCENARIO_DIR}", str(scenario_dir))
(scenario_dir / "compile_commands.json").write_text(resolved)
# clangd now reads the resolved file
```

Why not hard-code the absolute path: it would only work on one
developer machine. Why not use the directory field as `.` and resolve
relative paths: clangd's behavior on relative paths varies across
versions and operating systems.

## Pipeline

| Stage | File | Status |
|---|---|---|
| M28.0 | [`PRE_REGISTRATION.md`](PRE_REGISTRATION.md) | ✅ committed |
| M28.1 | `compile_commands.json` (templated) | ⚠️ authored, unvalidated (no clang installed locally) |
| M28.2 | `src/loom/indexers_cpp.py` | pending |
| M28.3 | `m28_clangd_smoke.py` | pending |
| M28.4 | sweep + verdict + finding capture | pending |

## Verification checklist (run before claiming M28.1 done)

1. `clangd --version` returns 17.x or later.
2. Substitute `${SCENARIO_DIR}` with the actual path and run
   `clang++ -std=c++17 -I<scenario>/reference -c <scenario>/tests/test_retry.cpp`.
   It should compile cleanly with no warnings under `-Wall -Wextra`.
3. Run `clangd --check=<scenario>/tests/test_retry.cpp` and check that
   it loads compile_commands.json and reports zero errors.

If any of these fail, surface as a finding in the loom store before
proceeding to M28.2.
