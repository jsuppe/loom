"""Acceptance tests for the R1 refactor — adding RegexField.

These tests must FAIL against the pre-refactor library (no RegexField
exists) and PASS after a correct refactor. Together with the
regression suite in test_pyschema.py they grade refactor outcomes:

  * regression failures → executor over-modified existing code
  * acceptance failures → refactor incomplete or incorrect
  * both pass            → clean refactor
"""

import pytest

from pyschema.field import RegexField
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
        # RegexField is a string-typed field — coercion + length
        # validation should still apply if min_length/max_length are
        # set, in addition to the pattern check.
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
