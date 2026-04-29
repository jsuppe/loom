"""Regression tests for the pyschema library.

These tests cover behavior that must be preserved across any refactor.
A correct R1 (add RegexField) refactor must leave every test in this
file passing untouched.
"""

import pytest

from pyschema import (
    BoolField,
    Choice,
    CoercionError,
    EmailField,
    IntField,
    MaxLength,
    MaxValue,
    MinLength,
    MinValue,
    Schema,
    SchemaDefinitionError,
    StrField,
    ValidationError,
)


# ---------------------------------------------------------------------------
# IntField
# ---------------------------------------------------------------------------

class TestIntField:
    def test_accepts_int(self):
        f = IntField()
        assert f.validate(42) == 42

    def test_coerces_numeric_string(self):
        f = IntField()
        assert f.validate("42") == 42

    def test_refuses_bool(self):
        f = IntField()
        with pytest.raises(CoercionError):
            f.validate(True)

    def test_min_value_enforced(self):
        f = IntField(min_value=10)
        with pytest.raises(ValidationError):
            f.validate(5)

    def test_max_value_enforced(self):
        f = IntField(max_value=10)
        with pytest.raises(ValidationError):
            f.validate(20)

    def test_required_default_raises_on_none(self):
        f = IntField()
        with pytest.raises(ValidationError):
            f.validate(None)

    def test_optional_returns_default(self):
        f = IntField(required=False, default=0)
        assert f.validate(None) == 0


# ---------------------------------------------------------------------------
# StrField
# ---------------------------------------------------------------------------

class TestStrField:
    def test_accepts_str(self):
        f = StrField()
        assert f.validate("hello") == "hello"

    def test_coerces_int_to_str(self):
        f = StrField()
        assert f.validate(42) == "42"

    def test_min_length_enforced(self):
        f = StrField(min_length=3)
        with pytest.raises(ValidationError):
            f.validate("ab")

    def test_max_length_enforced(self):
        f = StrField(max_length=3)
        with pytest.raises(ValidationError):
            f.validate("abcd")


# ---------------------------------------------------------------------------
# BoolField
# ---------------------------------------------------------------------------

class TestBoolField:
    def test_accepts_bool(self):
        f = BoolField()
        assert f.validate(True) is True

    def test_coerces_truthy_string(self):
        f = BoolField()
        assert f.validate("yes") is True
        assert f.validate("false") is False


# ---------------------------------------------------------------------------
# EmailField
# ---------------------------------------------------------------------------

class TestEmailField:
    def test_accepts_valid(self):
        f = EmailField()
        assert f.validate("a@x.com") == "a@x.com"

    def test_rejects_no_at(self):
        f = EmailField()
        with pytest.raises(ValidationError):
            f.validate("noat")

    def test_rejects_no_tld(self):
        f = EmailField()
        with pytest.raises(ValidationError):
            f.validate("a@x")


# ---------------------------------------------------------------------------
# Choice validator (used standalone via StrField.validators)
# ---------------------------------------------------------------------------

class TestChoiceValidator:
    def test_in_options_passes(self):
        f = StrField(validators=[Choice(["admin", "user"])])
        assert f.validate("admin") == "admin"

    def test_outside_options_raises(self):
        f = StrField(validators=[Choice(["admin", "user"])])
        with pytest.raises(ValidationError):
            f.validate("guest")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

class TestSchema:
    def test_schema_validates_all_fields(self):
        class UserSchema(Schema):
            name = StrField()
            age = IntField()

        out = UserSchema().validate({"name": "A", "age": 1})
        assert out == {"name": "A", "age": 1}

    def test_schema_attaches_field_name_to_error(self):
        class UserSchema(Schema):
            email = EmailField()

        try:
            UserSchema().validate({"email": "noat"})
        except ValidationError as exc:
            assert exc.field == "email"
        else:
            pytest.fail("expected ValidationError")

    def test_empty_schema_definition_raises(self):
        class EmptySchema(Schema):
            pass

        with pytest.raises(SchemaDefinitionError):
            EmptySchema()

    def test_schema_fields_property_returns_copy(self):
        class S(Schema):
            x = IntField()

        s = S()
        f1 = s.fields
        f1["mutated"] = None
        assert "mutated" not in s.fields


# ---------------------------------------------------------------------------
# Validators (standalone usage via Field.validators)
# ---------------------------------------------------------------------------

class TestValidatorsStandalone:
    def test_min_length_check_raises(self):
        with pytest.raises(ValidationError):
            MinLength(3).check("ab")

    def test_max_length_check_raises(self):
        with pytest.raises(ValidationError):
            MaxLength(2).check("abc")

    def test_min_value_check_raises(self):
        with pytest.raises(ValidationError):
            MinValue(10).check(5)

    def test_max_value_check_raises(self):
        with pytest.raises(ValidationError):
            MaxValue(10).check(20)
