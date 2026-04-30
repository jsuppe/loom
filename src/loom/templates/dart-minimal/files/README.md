# {{ app_name }}

{{ description }}

## Install (dev)

```bash
dart pub get
```

## Test

```bash
dart test
```

## Loom

This project is wired for Loom. `.loom-config.json` pins the `dart_test`
runner; `loom_exec` grades via `dart test path --plain-name Name`.

Typical flow:

```bash
loom extract                                             # capture a requirement
loom spec REQ-xxx -d "..." \
  --test test/foo_test.dart::SomeGroup                   # writes a failing-placeholder
loom decompose SPEC-xxx --apply                          # split into atomic tasks
loom_exec --next                                         # execute with qwen3.5
```
