"""Tests for the typelink (Milestone 7) data model + extractors."""

import json
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import typelink  # noqa: E402
from store import Symbol, Specification  # noqa: E402


# ---------------------------------------------------------------------------
# Symbol / Specification roundtrip
# ---------------------------------------------------------------------------

class TestSpecPublicApi:
    def test_specification_back_compat(self):
        # Old store data without public_api_json field still loads.
        old_metadata = {
            "id": "SPEC-x", "parent_req": "REQ-y",
            "description": "test", "timestamp": "2026-01-01",
        }
        s = Specification.from_dict(old_metadata)
        assert s.public_api_json == ""
        assert s.get_public_api() == {}

    def test_set_get_public_api(self):
        s = Specification(id="SPEC-x", parent_req="REQ-y",
                           description="d", timestamp="t")
        s.set_public_api({"foo.py": [{"name": "Foo", "kind": "class",
                                       "signature": "class Foo"}]})
        api = s.get_public_api()
        assert "foo.py" in api
        assert api["foo.py"][0]["name"] == "Foo"

    def test_empty_dict_serializes_empty_string(self):
        s = Specification(id="SPEC-x", parent_req="REQ-y",
                           description="d", timestamp="t")
        s.set_public_api({})
        assert s.public_api_json == ""


# ---------------------------------------------------------------------------
# Python extractor
# ---------------------------------------------------------------------------

class TestPythonExtractor:
    def test_class_with_methods(self, tmp_path):
        f = tmp_path / "shop.py"
        f.write_text(textwrap.dedent('''
            from dataclasses import dataclass

            @dataclass
            class Customer:
                id: str
                name: str
                _internal: int = 0

                def register(self, *, id: str, name: str) -> None:
                    pass

                def _private(self) -> None:
                    pass
        '''))
        symbols = typelink.python_extract(f)
        names = {s.name for s in symbols}
        assert "Customer" in names
        assert "Customer.id" in names
        assert "Customer.name" in names
        assert "Customer.register" in names
        # Private members are excluded.
        assert "Customer._internal" not in names
        assert "Customer._private" not in names

    def test_top_level_function(self, tmp_path):
        f = tmp_path / "util.py"
        f.write_text("def public_helper(x: int) -> int:\n    return x * 2\n")
        symbols = typelink.python_extract(f)
        names = {s.name for s in symbols}
        assert "public_helper" in names

    def test_invalid_syntax_returns_empty(self, tmp_path):
        f = tmp_path / "broken.py"
        f.write_text("def f(:\n")
        assert typelink.python_extract(f) == []


# ---------------------------------------------------------------------------
# Dart extractor (regex)
# ---------------------------------------------------------------------------

class TestDartExtractor:
    def test_class_with_named_constructor(self, tmp_path):
        f = tmp_path / "x.dart"
        f.write_text(textwrap.dedent('''
            class Address {
              final String street;
              final String city;
              const Address({required this.street, required this.city});
            }
        '''))
        symbols = typelink.dart_extract(f)
        names = {s.name for s in symbols}
        assert "Address" in names
        assert "Address.Address" in names
        assert "Address.street" in names
        assert "Address.city" in names

    def test_method_with_records_param(self, tmp_path):
        # The regex-can't-handle-nested-parens case from cpp-inventory
        # v2_01. Should be captured by the balanced-paren walker.
        f = tmp_path / "service.dart"
        f.write_text(textwrap.dedent('''
            class OrderService {
              Order place({required String customerId,
                           required List<({String sku, int quantity})> lines}) {
                throw UnimplementedError();
              }
            }
        '''))
        symbols = typelink.dart_extract(f)
        names = {s.name for s in symbols}
        assert "OrderService" in names
        assert "OrderService.place" in names

    def test_skips_method_body_contents(self, tmp_path):
        f = tmp_path / "x.dart"
        f.write_text(textwrap.dedent('''
            class Foo {
              void bar() {
                if (true) { throw Exception('hi'); }
                for (final i in []) { }
              }
            }
        '''))
        symbols = typelink.dart_extract(f)
        names = {s.name for s in symbols}
        assert "Foo" in names
        assert "Foo.bar" in names
        # Control-flow inside method body must not appear as methods.
        assert "Foo.if" not in names
        assert "Foo.for" not in names
        assert "Foo.Exception" not in names


# ---------------------------------------------------------------------------
# diff_symbols
# ---------------------------------------------------------------------------

class TestDiff:
    def test_missing_symbol(self):
        expected = [Symbol(name="Foo", kind="class", signature="class Foo"),
                    Symbol(name="Foo.x", kind="field", parent="Foo",
                           signature="int x")]
        got = [Symbol(name="Foo", kind="class", signature="class Foo")]
        diffs = typelink.diff_symbols(expected, got)
        assert any(d.kind == "missing_symbol" and d.symbol == "Foo.x"
                   for d in diffs)

    def test_signature_mismatch(self):
        expected = [Symbol(name="f", kind="function", signature="def f(x: int)")]
        got = [Symbol(name="f", kind="function", signature="def f(x: str)")]
        diffs = typelink.diff_symbols(expected, got)
        assert len(diffs) == 1
        assert diffs[0].kind == "signature_mismatch"

    def test_extra_symbol_is_informational(self):
        expected = [Symbol(name="A", kind="class", signature="class A")]
        got = [Symbol(name="A", kind="class", signature="class A"),
               Symbol(name="B", kind="class", signature="class B")]
        diffs = typelink.diff_symbols(expected, got)
        assert all(d.kind == "extra_symbol" for d in diffs)

    def test_is_additive(self):
        old = [Symbol(name="Foo", kind="class", signature="class Foo")]
        # Adding a method is additive.
        new_additive = old + [Symbol(name="Foo.bar", kind="method",
                                       parent="Foo", signature="void bar()")]
        assert typelink.is_additive(old, new_additive)
        # Removing a member is not additive.
        assert not typelink.is_additive(new_additive, old)


# ---------------------------------------------------------------------------
# Contract-fence extraction (Q6 default authorship path)
# ---------------------------------------------------------------------------

class TestContractFenceExtraction:
    def test_dart_contract_block_to_public_api(self):
        spec_text = textwrap.dedent('''
            ### lib/types/customers.dart

            Customer + Address types.

            ```dart-contract
            class Address {
              final String street;
              final String city;
              const Address({required this.street, required this.city});
            }
            ```

            ### lib/errors.dart

            ```dart-contract
            class DomainError implements Exception {
              final String message;
              DomainError(this.message);
            }
            ```
        ''')
        api = typelink.extract_public_api_from_spec(spec_text)
        assert "lib/types/customers.dart" in api
        assert "lib/errors.dart" in api
        cust_names = {s["name"] for s in api["lib/types/customers.dart"]}
        assert "Address" in cust_names
        assert "Address.street" in cust_names

    def test_no_fences_returns_empty(self):
        spec_text = "### lib/x.dart\n\nJust prose, no fences.\n"
        assert typelink.extract_public_api_from_spec(spec_text) == {}

    def test_unknown_fence_language_skipped(self):
        spec_text = textwrap.dedent('''
            ### lib/x.swift

            ```swift-contract
            class Whatever {}
            ```
        ''')
        # No swift verifier registered → skipped silently.
        assert typelink.extract_public_api_from_spec(spec_text) == {}
