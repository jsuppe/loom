# Requirement Extraction Prompt

You are analyzing a conversation to extract requirements. A requirement is a decision about how something should work, what something should be called, how data should be structured, or any other constraint that affects implementation.

## Input
A conversation transcript or message.

## Output
For each requirement found, output a line in this format:
```
REQUIREMENT: <domain> | <requirement text>
```

## Domains

- **terminology** — Naming decisions ("posts are called boats", "app name is SpeakFit not SpeechScore")
- **behavior** — How features work ("reset requires 3-second hold", "timer pauses when app is backgrounded")
- **ui** — Visual/UX decisions ("mobile-friendly", "no markdown tables on Discord", "LEGO style for 3D")
- **data** — Data model constraints ("time rounds down to half-hour", "outbursts allow multiple moods")
- **architecture** — Technical decisions ("ChromaDB for vectors", "Flutter + FastAPI stack")

## Guidelines

1. Be specific — Include concrete details, not vague statements
2. One requirement per line — Don't combine multiple decisions
3. Skip obvious things — "The app should work" is not a requirement
4. Capture constraints — Things that limit options are important
5. Note supersessions — If a requirement contradicts an earlier one, extract both

## Examples

Input: "The app should use half-hour increments for time selection, and times should round down not up"

Output:
```
REQUIREMENT: data | Time selection uses half-hour increments
REQUIREMENT: behavior | Time input rounds down to previous half-hour (not up)
```

Input: "Actually, let's call it SpeakFit instead of SpeechScore"

Output:
```
REQUIREMENT: terminology | App name is SpeakFit (not SpeechScore)
```
