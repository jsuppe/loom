# Failure-Mode Audit

Total failed trials: **163**

- Multi-file benchmark failures: 28
- Single-file benchmark failures: 135

## Typelink-shaped fraction

- Multi-file failures classified as typelink-shaped: **27 / 28 (96.4%)**
- Single-file failures classified as typelink-shaped: 0 / 135 (0.0%)

## Categories — multi-file failures

- `missing_symbol`: 16 (57.1%) ←typelink
- `signature_mismatch`: 8 (28.6%) ←typelink
- `missing_definition_link`: 3 (10.7%) ←typelink
- `test_logic_fail`: 1 (3.6%)

## Categories — single-file failures

- `no_diagnostic`: 112 (83.0%)
- `other`: 23 (17.0%)

## Per-phase breakdown — multi-file failures

| phase | total fail | typelink | typelink % |
|---|---:|---:|---:|
| C/cpp-inv | 4 | 4 | 100.0% |
| C/dart-inv | 9 | 9 | 100.0% |
| C/dart-orders | 12 | 11 | 91.7% |
| C/flutter | 3 | 3 | 100.0% |

## Sample failure snippets

### `missing_definition_link` (3 failures)
- **phC_cpp_inv_runc01_summary** (multi): `N5SetupC1Ev[_ZN5SetupC1Ev]+0x137): undefined reference to `CustomerService::register_customer(std::__cxx11::basic_string<char, std::char_traits<char>, std::allo`
- **phC_cpp_inv_runc02_summary** (multi): `N5SetupC1Ev[_ZN5SetupC1Ev]+0x137): undefined reference to `CustomerService::register_customer(std::__cxx11::basic_string<char, std::char_traits<char>, std::allo`
- **phC_cpp_inv_runc05_summary** (multi): `C:/mingw64/bin/../lib/gcc/x86_64-w64-mingw32/14.2.0/../../../../x86_64-w64-mingw32/bin/ld.exe: C:\Users\jonsu\AppData\Local\Temp\cclI6vup.o:shop_test.cpp:(.text`

### `missing_symbol` (16 failures)
- **phC_dart_inv_rund01_summary** (multi): `:32: Error: 'OrderService' isn't a type.`
- **phC_dart_inv_rund02_summary** (multi): `:32: Error: 'OrderService' isn't a type.`
- **phC_dart_inv_rund04_summary** (multi): `:32: Error: 'OrderService' isn't a type.`

### `no_diagnostic` (112 failures)
- **phA_haiku_sym_haikupo-haikueng-noneL-python-queue_001** (single): ``
- **phB_haiku_sym_haikupo-haikueng-engL-python-state-machine_003** (single): ``
- **phD_auto_run1_summary** (single): ``

### `other` (23 failures)
- **phE_hook_smoke_all_haiku#0** (single): `uses os.environ/getenv (violation)`
- **phE_hook_smoke_all_haiku#1** (single): `uses os.environ/getenv (violation)`
- **phE_hook_smoke_all_haiku#2** (single): `uses os.environ/getenv (violation)`

### `signature_mismatch` (8 failures)
- **phC_cpp_inv_runv2_01_summary** (multi): `test/shop_test.cpp:74:60: error: no matching function for call to 'Address::Address(<brace-enclosed initializer list>)'`
- **phC_dart_inv_rund03_summary** (multi): `[exec] result: {"task_id": "TASK-c63bcc4756bf", "outcome": "test_fail", "passed": 0, "total": 1, "tail": "                   ^^^^^^^^^^^^^^^^^^^^^^\n  test/_gat`
- **phC_dart_inv_rund05_summary** (multi): `[exec] result: {"task_id": "TASK-efdd283f17d1", "outcome": "test_fail", "passed": 0, "total": 1, "tail": "  lib/types/customers.dart:8:9: Context: Found this ca`

### `test_logic_fail` (1 failures)
- **phC_dart_run3_summary** (multi): `test/orders_test.dart:9:6: Error: Type 'Item' not found.`
