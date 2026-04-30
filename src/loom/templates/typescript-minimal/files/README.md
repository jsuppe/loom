# {{ app_name }}

{{ description }}

## Install (dev)

```bash
npm install
```

## Test

```bash
npm test
```

## Build

```bash
npm run build
```

## Loom

This project is wired for Loom. `.loom-config.json` pins the `vitest`
runner; `loom_exec` grades via `npx vitest run path -t Name`.

Typical flow:

```bash
loom extract                                              # capture a requirement
loom spec REQ-xxx -d "..." \
  --test tests/foo.test.ts::SomeDescribe                  # writes a failing-placeholder
loom decompose SPEC-xxx --apply                           # split into atomic tasks
loom_exec --next                                          # execute with qwen3.5
```
