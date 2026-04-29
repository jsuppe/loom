# pyschema benchmark

A small declarative validation library — `Schema` declares named
`Field` instances; each field handles coercion, validation, and
defaults. Used as the substrate for both the C scaling ramp (greenfield
construction at varying file counts) and the D refactor smoke
(R1 = add `RegexField`).

## Public API

```python
from pyschema import (
    Schema,
    IntField, StrField, BoolField, EmailField,
    Choice, MinLength, MaxLength, MinValue, MaxValue,
    ValidationError, CoercionError, SchemaDefinitionError,
)


class UserSchema(Schema):
    name = StrField(min_length=1, max_length=80)
    age = IntField(min_value=0, max_value=200)
    email = EmailField()
    role = StrField(validators=[Choice(["admin", "user"])])


cleaned = UserSchema().validate({
    "name": "Alice",
    "age": 30,
    "email": "alice@example.com",
    "role": "admin",
})
```

## Files (6 executor tasks + 1 pre-written barrel for greenfield builds)

```
pyschema/
├── __init__.py          (barrel — pre-written by harness in greenfield mode)
├── errors.py            [task 1]   exceptions
├── coercion.py          [task 2]   coerce_int / coerce_str / coerce_bool
├── validators.py        [task 3]   MinLength, MaxLength, MinValue, MaxValue, Choice
├── field.py             [task 4]   Field base + IntField/StrField/BoolField/EmailField
└── schema.py            [task 5]   Schema class
```

For the **D refactor smoke**, the executor receives the library
pre-written and must apply the R1 refactor described below.

## Domain model (REQ-1 through REQ-5)

### REQ-1: Error hierarchy (`errors.py`)

A small hierarchy rooted at `SchemaError(Exception)`:

- `SchemaError` — base type
- `ValidationError(SchemaError)` — value failed a validator. Holds
  `.message: str` and `.field: str` (set by `Schema.validate`)
- `CoercionError(SchemaError)` — value cannot be coerced to target type
- `SchemaDefinitionError(SchemaError)` — Schema construction is invalid
  (e.g. zero declared fields)

### REQ-2: Coercion helpers (`coercion.py`)

Three narrow helpers that raise `CoercionError` on failure:

- `coerce_int(value)`: accepts `int` (not `bool`!), numeric `str`. Refuses
  bool — `coerce_int(True)` raises (bool would silently coerce to `1`).
- `coerce_str(value)`: accepts `str`, `int`, `float`, `bool` and stringifies.
- `coerce_bool(value)`: accepts `bool`, `int`, and case-insensitive
  `"true"/"false"/"1"/"0"/"yes"/"no"/"on"/"off"`.

### REQ-3: Validators (`validators.py`)

Five small frozen dataclasses each exposing a `check(value)` method
that raises `ValidationError` on failure:

- `MinLength(n)` / `MaxLength(n)` for sequences (typically strings)
- `MinValue(n)` / `MaxValue(n)` for ints/floats
- `Choice(options)` — value must be in the options tuple. Stored as a
  tuple internally so the dataclass remains hashable/frozen.

### REQ-4: Fields (`field.py`)

Base `Field` dataclass with attributes `required: bool = True`,
`default: Any = None`, `validators: List[Any] = []`. Method
`validate(value)` is the entry point: if `value is None`, raise
`ValidationError` if required else return default; otherwise coerce
then run all validators in order.

Concrete subclasses:

- `IntField(min_value=None, max_value=None)` — coerces via `coerce_int`.
  In `__post_init__`, appends `MinValue/MaxValue` validators when set.
- `StrField(min_length=None, max_length=None)` — coerces via `coerce_str`.
  `__post_init__` appends `MinLength/MaxLength`.
- `BoolField()` — coerces via `coerce_bool`.
- `EmailField`: subclass of `StrField` that overrides `validate` to
  also require the value match a basic `^[^@\s]+@[^@\s]+\.[^@\s]+$` regex.

### REQ-5: Schema (`schema.py`)

Class-level field declaration model:

```python
class S(Schema):
    name = StrField(...)
    age = IntField(...)
```

`__init__` walks `dir(type(self))`, finds class attributes that are
`Field` instances, stores them in `self._fields`. Raises
`SchemaDefinitionError` if no fields declared.

`validate(data)` calls each field's `validate(data.get(name))` and
attaches the field name to any `ValidationError` raised.

`fields` property returns a **copy** of the internal field dict so
external mutation can't corrupt schema state.

## R1 refactor task (D smoke target)

Add a `RegexField` type that:

- Inherits from `StrField` (so it gets length validators + str coercion).
- Adds a single `pattern: str` attribute.
- Overrides `validate(value)` to apply the parent's check, then
  reject any value that does not match `pattern`.
- Is exported from `pyschema/__init__.py` (alphabetically sorted in
  `__all__`).

The acceptance test suite is `tests/test_regexfield.py`. A correct
refactor leaves the regression suite (`tests/test_pyschema.py`) at
26/26 and brings the acceptance suite from collection-error to 6/6.
