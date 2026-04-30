"""Acceptance tests for R6 — adding RegexField to pyschema-extended.

These tests must FAIL against the pre-refactor library (no RegexField)
and PASS after a correct refactor. The refactor task: add a
``RegexField(StrField)`` that takes ``pattern: str`` and validates
inputs against the pattern.
"""

import pytest

from pyschema.fields.strings import RegexField
from pyschema.errors import ValidationError
from pyschema.schema import Schema


class TestRegexField:
    def test_construct_with_pattern(self):
        f = RegexField(pattern=r"^[a-z]+$")
        assert f.pattern == r"^[a-z]+$"

    def test_validate_matching_value(self):
        f = RegexField(pattern=r"^[a-z]+$")
        assert f.validate("abc") == "abc"

    def test_validate_rejects_nonmatching_value(self):
        f = RegexField(pattern=r"^[a-z]+$")
        with pytest.raises(ValidationError):
            f.validate("ABC")

    def test_inherits_strfield_behavior(self):
        # min_length/max_length still apply because RegexField extends StrField
        f = RegexField(pattern=r"^.+$", min_length=3)
        assert f.validate("abcd") == "abcd"
        with pytest.raises(ValidationError):
            f.validate("ab")

    def test_works_inside_schema(self):
        class IDSchema(Schema):
            handle = RegexField(pattern=r"^@[a-z0-9_]{3,15}$")

        s = IDSchema()
        assert s.validate({"handle": "@alice_99"})["handle"] == "@alice_99"
        with pytest.raises(ValidationError) as exc_info:
            s.validate({"handle": "alice"})
        assert exc_info.value.field == "handle"
