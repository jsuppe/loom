# Implementation Linking Prompt

You are analyzing code to determine which requirements it satisfies.

## Input
1. Code snippet (file path and content)
2. List of candidate requirements

## Output
For each requirement the code satisfies, output:
```
SATISFIES: <requirement-id>
```

## Guidelines

1. **Direct implementation** — Code that directly implements the requirement
2. **Enforcement** — Code that enforces a constraint (validation, rounding, etc.)
3. **Partial** — If code partially satisfies a requirement, still include it
4. **Skip tangential** — Don't link just because code mentions related concepts

## Example

Code: `lib/widgets/time_picker.dart`
```dart
int roundToHalfHour(int minutes) {
  return (minutes ~/ 30) * 30;  // Round DOWN to nearest 30
}
```

Candidate requirements:
- REQ-001: Time selection uses half-hour increments
- REQ-002: Time input rounds down to previous half-hour (not up)
- REQ-003: Calendar shows 7-day view

Output:
```
SATISFIES: REQ-001
SATISFIES: REQ-002
```

(REQ-003 is unrelated to this code)
