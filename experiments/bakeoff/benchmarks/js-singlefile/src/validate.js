// Reference solution for s_validate.
//
// Public contract:
//   validate(input, rules) -> { valid: boolean, errors: Array<{field, message}> }
//
//   input: an object whose fields will be checked
//   rules: array of rule objects { field: string, check: (value) => boolean, message: string }
//          A rule passes iff check(input[field]) returns truthy.
//
// Style (M22e s_validate rationale): collect ALL errors before returning.
// Never short-circuit on the first failure. Each rule is evaluated; failing
// rules contribute an entry to the errors array.

export function validate(input, rules) {
  const errors = [];
  if (input === null || input === undefined || typeof input !== 'object') {
    return { valid: false, errors: [{ field: '*', message: 'input must be an object' }] };
  }
  if (!Array.isArray(rules)) {
    return { valid: false, errors: [{ field: '*', message: 'rules must be an array' }] };
  }
  for (const rule of rules) {
    let passed;
    try {
      passed = rule.check(input[rule.field]);
    } catch (err) {
      passed = false;
    }
    if (!passed) {
      errors.push({ field: rule.field, message: rule.message });
    }
  }
  return { valid: errors.length === 0, errors };
}
