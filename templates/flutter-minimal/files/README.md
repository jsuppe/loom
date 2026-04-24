# {{ app_name }}

{{ description }}

## Install (dev)

```bash
flutter pub get
```

## Test

```bash
flutter test
```

## Run the app

```bash
flutter run
```

## Loom

This project is wired for Loom. `.loom-config.json` pins the
`flutter_test` runner; `loom_exec` grades via
`flutter test path --plain-name Name`.

Typical flow:

```bash
loom extract                                            # capture a requirement
loom spec REQ-xxx -d "..." \
  --test test/counter_test.dart::Counter                # writes a failing-placeholder
loom decompose SPEC-xxx --apply                         # split into atomic tasks
loom_exec --next                                        # execute with qwen3.5
```
