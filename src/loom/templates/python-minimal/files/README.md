# {{ app_name }}

{{ description }}

## Install (dev)

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Test

```bash
pytest
```

## Loom

This project is wired for Loom — requirements, specifications, and
task-driven small-model execution. See `.loom-config.json` for the
pinned settings (project name, executor model, test dir, etc.).

Typical flow:

```bash
loom extract                                  # capture a requirement
loom spec REQ-xxx -d "..." --test tests/test_xxx.py::TestXxx
loom decompose SPEC-xxx --apply               # split into atomic tasks
loom_exec --next                              # execute with local model
```
