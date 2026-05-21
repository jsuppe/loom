# Intake-hook precision audit (M14.1)

Run against `intake_audit_labels.json`. Generated from
`.intake-log.jsonl` capturing branches
(`auto_link` + `captured_with_rationale`).

## Headline numbers

- Total captures: **25**
- Labeled: **25** (100.0% coverage)
- Real (y): **11**
- Noise (n): **9**
- Borderline (?): **5**

- **Precision (strict, n=noise)**: 0.550 (11/20)
- **Precision (lenient, ? counted as good)**: 0.640 (16/25)

## By kind

| kind | total | noise | precision |
|---|---|---|---|
| finding | 4 | 0 | 1.000 |
| hypothesis | 3 | 2 | 0.333 |
| methodology | 3 | 0 | 1.000 |
| process_rule | 5 | 3 | 0.400 |
| requirement | 10 | 4 | 0.600 |

## Noise captures (label=n)

### REQ-8a9f714b — requirement

- value: Implement the m11.3 feature.
- rationale: please implement the the m11.3
- audit note: One-time instruction ("please implement m11.3"). Vague + task-scoped, not a forever rule.

### REQ-e9aa56bc — process_rule

- value: Both loom and drift graph development are hosted on the same machine, allowing local access to drift graph source code and documentation within the SDR graph database repository.
- rationale: please note that both loom and drift graph development are under the same host, so you should be able to see drift graph source code and documentation locally in the SDR graph database repository
- audit note: Environment fact ("both projects on same host"), not a system rule. Classifier captured it because it parses as imperative.

### REQ-4293cb48 — hypothesis

- value: We hypothesize that the system's performance on development tasks will be measurable relative to a control.
- rationale: I'm interested to see if we can try development tasks to see how well this system performs relative to a control
- audit note: Speculation framed as hypothesis ("I'm interested to see if..."). Not a falsifiable claim; no defined experiment.

### REQ-b5cdf541 — hypothesis

- value: We should design a rigorous experiment using a large synthetic dataset of diverse scenarios to validate system detection capabilities and ensure the system is not overfitting to the synthetic data.
- rationale: I'm thinking we may want to create a very large synthetic data set of many different scenarios of which we want to be able to flag or track so that we can validate that this works across many different scenarios... what kind of experiment do you think we can create such that it is more rigorous in t
- audit note: Wishful brainstorm framed as hypothesis. "What kind of experiment do you think we can create?" is a question, not a hypothesis.

### REQ-b1eca25c — process_rule

- value: Responses should be formatted and written to a file on the shared file system, with the file path provided to the user.
- rationale: Yes, I would like you to format the response and write it to a file on the file system and then give me the path to the file on the file system.
- audit note: One-time instruction ("Yes, I would like you to format the response and write it to a file"). Session-scoped command, not a rule.

### REQ-c17b7a6f — process_rule

- value: Do not commit the counterfactual ablation file to version control.
- rationale: no need to commit this file
- audit note: File-specific one-time instruction ("no need to commit this file"). The exact opposite of a forever rule.

### REQ-c0907768 — requirement

- value: The system must continue execution without an API key and utilize the maximum setting for the rationale arc replication.
- rationale: Ok I'd like you to continue without the API key and use max for the rationale arc replication
- audit note: KNOWN NOISE — one-time instruction ("Ok I'd like you to continue without the API key"). Already archived in M14.5 cleanup.

### REQ-13af719e — requirement

- value: fetchWithRetry must catch and swallow errors thrown by doFetch on every attempt and return null when all attempts fail, without propagating errors.
- rationale: catch and swallow errors thrown by doFetch on every attempt. Do NOT propagate errors from this function. Return null when all attempts fail.
- audit note: KNOWN NOISE — scenario fragment from S1_js bake-off contrarian rule. Classifier captured it as a project requirement. Archived in M14.5.

### REQ-accfaacc — requirement

- value: The system must send a PushNotification only if the monitored event requires immediate user action, otherwise it should remain silent.
- rationale: If this event is something the user would act on now, send a PushNotification. Routine or benign output doesn't need one.
- audit note: KNOWN NOISE — tool docs ("If this event is something the user would act on now, send a PushNotification"). Pasted documentation, not a requirement for this project. Archived in M14.5.
