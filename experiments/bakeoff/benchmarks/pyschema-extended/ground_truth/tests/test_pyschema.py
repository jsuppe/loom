"""Regression tests for pyschema-extended.

These tests cover behavior that must be preserved across any refactor.
A correct R6 (add RegexField) refactor must leave every test in this
file passing untouched.
"""

import pytest
from datetime import date, datetime
from decimal import Decimal

from pyschema import (
    BoolField, Choice, CoercionError,
    DateField, DateTimeField, EmailField, Field, IntField,
    MaxLength, MaxValue, MinLength, MinValue, NonEmpty, Pattern,
    Schema, SchemaDefinitionError, SchemaNotRegisteredError,
    SchemaRegistry, StrField, URLField, UUIDField, ValidationError,
)


# ---------------------------------------------------------------------------
# IntField (7)
# ---------------------------------------------------------------------------

class TestIntField:
    def test_accepts_int(self):
        assert IntField().validate(42) == 42

    def test_coerces_numeric_string(self):
        assert IntField().validate("42") == 42

    def test_refuses_bool(self):
        with pytest.raises(CoercionError):
            IntField().validate(True)

    def test_min_value_enforced(self):
        with pytest.raises(ValidationError):
            IntField(min_value=10).validate(5)

    def test_max_value_enforced(self):
        with pytest.raises(ValidationError):
            IntField(max_value=10).validate(20)

    def test_required_default_raises_on_none(self):
        with pytest.raises(ValidationError):
            IntField().validate(None)

    def test_optional_returns_default(self):
        assert IntField(required=False, default=0).validate(None) == 0


# ---------------------------------------------------------------------------
# StrField (4)
# ---------------------------------------------------------------------------

class TestStrField:
    def test_accepts_str(self):
        assert StrField().validate("hello") == "hello"

    def test_coerces_int(self):
        assert StrField().validate(42) == "42"

    def test_min_length_enforced(self):
        with pytest.raises(ValidationError):
            StrField(min_length=3).validate("ab")

    def test_max_length_enforced(self):
        with pytest.raises(ValidationError):
            StrField(max_length=3).validate("abcd")


# ---------------------------------------------------------------------------
# BoolField (3)
# ---------------------------------------------------------------------------

class TestBoolField:
    def test_accepts_bool(self):
        assert BoolField().validate(True) is True

    def test_coerces_yes(self):
        assert BoolField().validate("yes") is True

    def test_coerces_false_string(self):
        assert BoolField().validate("false") is False


# ---------------------------------------------------------------------------
# EmailField (3)
# ---------------------------------------------------------------------------

class TestEmailField:
    def test_accepts_valid(self):
        assert EmailField().validate("a@x.com") == "a@x.com"

    def test_rejects_no_at(self):
        with pytest.raises(ValidationError):
            EmailField().validate("noat")

    def test_rejects_no_tld(self):
        with pytest.raises(ValidationError):
            EmailField().validate("a@x")


# ---------------------------------------------------------------------------
# URLField (3)
# ---------------------------------------------------------------------------

class TestURLField:
    def test_accepts_https(self):
        assert URLField().validate("https://example.com") == "https://example.com"

    def test_accepts_http_with_path(self):
        assert URLField().validate("http://x.com/path") == "http://x.com/path"

    def test_rejects_no_scheme(self):
        with pytest.raises(ValidationError):
            URLField().validate("example.com")


# ---------------------------------------------------------------------------
# UUIDField (2)
# ---------------------------------------------------------------------------

class TestUUIDField:
    def test_accepts_canonical(self):
        UUIDField().validate("550e8400-e29b-41d4-a716-446655440000")

    def test_rejects_no_dashes(self):
        with pytest.raises(ValidationError):
            UUIDField().validate("550e8400e29b41d4a716446655440000")


# ---------------------------------------------------------------------------
# DateField (3)
# ---------------------------------------------------------------------------

class TestDateField:
    def test_iso_string(self):
        assert DateField().validate("2026-04-30") == date(2026, 4, 30)

    def test_date_passthrough(self):
        d = date(2020, 1, 1)
        assert DateField().validate(d) == d

    def test_min_date(self):
        with pytest.raises(ValidationError):
            DateField(min_date=date(2025, 1, 1)).validate("2020-01-01")


# ---------------------------------------------------------------------------
# DateTimeField (2)
# ---------------------------------------------------------------------------

class TestDateTimeField:
    def test_iso(self):
        DateTimeField().validate("2026-04-30T12:00:00")

    def test_invalid(self):
        with pytest.raises(CoercionError):
            DateTimeField().validate("not-a-date")


# ---------------------------------------------------------------------------
# Validators standalone (5)
# ---------------------------------------------------------------------------

class TestValidators:
    def test_min_length(self):
        with pytest.raises(ValidationError):
            MinLength(3).check("ab")

    def test_max_length(self):
        with pytest.raises(ValidationError):
            MaxLength(2).check("abc")

    def test_choice(self):
        with pytest.raises(ValidationError):
            Choice(["a", "b"]).check("c")

    def test_pattern(self):
        with pytest.raises(ValidationError):
            Pattern(r"^[a-z]+$").check("ABC")

    def test_nonempty(self):
        with pytest.raises(ValidationError):
            NonEmpty().check("")


# ---------------------------------------------------------------------------
# Schema (3)
# ---------------------------------------------------------------------------

class TestSchema:
    def test_validates(self):
        class S(Schema):
            name = StrField()
            age = IntField()

        out = S().validate({"name": "A", "age": 1})
        assert out == {"name": "A", "age": 1}

    def test_attaches_field_name(self):
        class S(Schema):
            email = EmailField()

        with pytest.raises(ValidationError) as exc_info:
            S().validate({"email": "noat"})
        assert exc_info.value.field == "email"

    def test_empty_schema_raises(self):
        class E(Schema): pass

        with pytest.raises(SchemaDefinitionError):
            E()


# ---------------------------------------------------------------------------
# SchemaRegistry (3)
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_register_and_get(self):
        class S(Schema):
            x = IntField()

        r = SchemaRegistry()
        r.register("s", S)
        assert r.get("s") is S

    def test_unregistered_raises(self):
        with pytest.raises(SchemaNotRegisteredError):
            SchemaRegistry().get("missing")

    def test_register_non_schema_raises(self):
        with pytest.raises(TypeError):
            SchemaRegistry().register("x", str)
