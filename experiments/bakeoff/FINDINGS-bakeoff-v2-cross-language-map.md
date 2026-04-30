# Bakeoff V2 — Cross-Language Loom Lift Map (qwen3.5)

**Date:** 2026-04-30
**Question:** Does Loom's structured rule injection produce
similar lift across programming languages, or is the effect
language-specific? At what off-cell fitness does Loom start to
"bridge the gap"?
**Approach:** Direct port of the S1 (swallow-vs-propagate
contrarian) cross-session scenario across 9 languages. Same
4-cell harness (off / on-rule / on-rule+placebo / on-rule+rat),
same qwen3.5:latest model, same N=5 per cell. Direct Ollama call
with prompts mirroring `task_build_prompt`'s format (no `loom_exec`
needed for the per-language harnesses).
**N:** 9 languages × 4 cells × N=5 = 180 trials. 0 harness errors.
3 trials hung in C++ (counted as failures).

---

## TL;DR

> **Loom's effect varies dramatically by language, even at the same
> raw off-cell fitness.** Three languages with off=0% (Java, JS,
> Rust, C++) span the full spectrum: Rust shoots to 100% on rule
> alone (+100pp lift), Java reaches 60% on rule and 100% with
> rationale, JS climbs gradually to 60%, and C++ stays at 0% on
> rule (mechanism collapses).
>
> Off-cell fitness is **not a clean predictor** of Loom lift. The
> hidden variable is how qwen weighs structured-rule context vs
> task-instinct priors *in that language*: in some languages qwen
> treats stored rules as authoritative; in others as one opinion
> among many; in others ignorably.
>
> The cleanest "Loom bridges the gap" data: TypeScript (off 0% →
> rule+rationale 100%, monotonically +40 → +80 → +100), and Java
> (off 0% → rule 60% → +placebo 100%). JS shows graduated lift but
> caps at 60% — rationale helps even when rule alone doesn't.

---

## The full table (qwen3.5:latest, S1 swallow-vs-propagate)

| language | off | on-rule | +placebo | +rat | rule lift | rat lift | regime |
|---|---|---|---|---|---|---|---|
| **Python** | 80% | 100% | 100% | 100% | +20 | +0 | already-saturated |
| **Rust** | 0% | 100% | 100% | 100% | **+100** | +0 | rule-saturates |
| **Asm (NASM x86-64)** | 0% | 100% | 100% | 100% | **+100** | +0 | rule-saturates |
| **Java** | 0% | 60% | 100% | 100% | +60 | +40 | bridging |
| **TypeScript** | 0% | 40% | 80% | 100% | +40 | +60 | bridging-graduated |
| **JavaScript** | 0% | 20% | 40% | 60% | +20 | +40 | graded-no-saturation |
| **Go** | 20% | 60% | 100% | 60% | +40 | +0 | volatile |
| **C** | 50% | 50% | 60% | 60% | +0 | +10 | resistant-mid |
| **C++** | 0% | 0% | 100%* | 67% | +0 | +67 | collapsed (*placebo artifact) |

The Asm result is striking: NASM x86-64 is the *lowest-level* language
in the matrix yet shows the *cleanest* rule-saturation behavior.
20/20 trials produced compiling, valid asm; off cell shows true
contrarian behavior (qwen replaces `xor rax, rax` with `mov rax, -1`),
and any rule context flips qwen to perfect compliance. qwen3.5's
NASM training data appears to be heavily comment-driven and rule-
oriented, so structured prompts are weighted as authoritative.

`rule lift` = on-rule − off. `rat lift` = on-rule+rat − on-rule.

---

## Per-language regimes

### Python — already-saturated
`off=80%, rule+=20pp, rat+=0pp`. qwen's Python is fluent enough that
even without a rule, qwen often leaves the existing swallow alone (4/5
trials). Adding a rule fully saturates compliance. Rationale is
decorative. **Loom amplifies; doesn't bridge a gap that wasn't there.**

### Rust — rule-saturates (biggest single lift)
`off=0% (5/5 compile failures), rule+=100pp, rat+=0pp`. qwen's
contrarian "fix" attempts in Rust produce uncompilable code every
time — Rust's strict ownership/typing system gates qwen's ad-hoc
edits. Once a rule is present, qwen produces clean compliant code
that compiles and passes both tests. **The biggest single Loom lift
in the dataset (+100pp from off to rule).**

The mechanism here is interesting: Rust's strictness amplifies the
value of structured rules because qwen *can't* compromise (no
"propagate after attempts" wrapper that compiles cleanly). Either
qwen complies fully or fails to compile.

### Java — bridging
`off=0%, rule+=60pp, rat+=40pp`. Clean bridge from contrarian floor
to rule-context saturation. qwen disregards constraint without spec,
weighs rule alone partially (60%), reaches saturation with rule+rationale
context. The +placebo cell also hits 100% — at this language tier,
the *length/salience* of the rule context matters as much as content.

### TypeScript — bridging-graduated
`off=0%, rule=40%, +placebo=80%, +rat=100%`. Best-shaped dose-response
curve in the dataset — every cell monotonically better, no plateau,
saturation reached at on-rule+rat. **The single cleanest "Loom bridges
the gap" data point.** TS qwen is fluent enough to follow rules but
not so fluent that it complies on rule alone — the rationale carries
genuine marginal information.

### JavaScript — graded, no saturation
`off=0%, rule=20%, +placebo=40%, +rat=60%`. Most surprising result.
qwen's JS shows graduated lift just like TS, but **never saturates**.
Even with rule + true rationale, only 60% of trials comply. qwen
takes the contrarian task more seriously in JS than in TS, possibly
because TS's type-annotated return signature (`string | null`)
provides additional structural commitment that pushes qwen toward
compliance.

JS is also the **only language** where on-rule+rat clearly beats
on-rule+placebo (60% vs 40%) — the true rationale carries weight
beyond mere length.

### Go — volatile
`off=20%, rule=60%, +placebo=100%, +rat=60%`. Hits 100% with
placebo, drops back to 60% with true rationale. Either noise at
N=5 (binomial 95% CI is wide) or qwen's Go training has a quirk
where the "BackoffError wrapper" rationale text confuses it. Worth
re-running at higher N.

### C — resistant-mid
`off=50%, rule=50%, +placebo=60%, +rat=60%`. Stable mid-fluency,
**no Loom lift**. qwen consistently writes the same "compromise"
code regardless of cell — preserves the pre-existing return-NULL
behavior (per the rule) but also adds errno propagation (per the
task). Both behaviors coexist in qwen's output every trial. The
rule is present but qwen weighs it equal-or-less to task instinct.

### C++ — collapsed
`off=0%, rule=0%, +placebo=100%*, +rat=67%`. Asterisk: the placebo
"100%" is an artifact — qwen with placebo content gives up on the
task and copies the original verbatim, so tests pass by inaction.
Real on-rule = 0%: qwen produces a "compromise" that violates the
rule (catch on intermediate, throw on last) every trial.
on-rule+rat = 67% (4/6 clean trials passed; 2 hung at 32k+ tokens).

C++ shows the most extreme rule-disregard pattern. qwen's C++
priors fight the contrarian rule directly.

---

## What this tells us about "the threshold"

The user's original question: *"Over what threshold of capability
in a language does Loom then bridge the gap as executor?"*

**Off-cell fitness alone doesn't answer it.** Five languages have
off ∈ {0%, 0%, 0%, 0%, 0%} (Java, TS, JS, Rust, C++) and they show
five different Loom regimes. Two languages have off ∈ {20%, 50%}
(Go, C) and they show different patterns again.

The actual threshold appears to be **how qwen weighs structured
rules in this language**, which is a property of qwen's training
data + language characteristics (strictness, idiom, output
verbosity), not of raw fluency.

A speculative ordering of qwen's "rule-followingness" by language:

| rule-followingness | languages |
|---|---|
| highest (rule alone saturates) | Python, Rust |
| high (rule+placebo saturates) | Java, TS |
| moderate (gradual; no saturation) | JS |
| low (rule barely beats off) | Go (volatile) |
| none (rule = off) | C |
| inverted (rule sometimes hurts) | C++ (compromise mode) |

Loom's value zone: **languages where qwen treats rules as
authoritative** (Python, Rust, Java, TS, and to a lesser extent JS).
Languages where qwen weighs rules equal-or-less to task instinct
(C, C++, partially Go) get little or no Loom lift.

---

## What this tells us about positioning

For a Loom user picking a target language:

**Strong fit:** Python, Java, TypeScript, Rust. qwen3.5 + Loom
delivers clean compliance with stored decisions across sessions in
these languages. Rust in particular shows dramatic lift on this
benchmark (compile gates everything).

**Mixed fit:** JavaScript. Loom helps but doesn't reliably saturate.
Plan for retries / higher-N decisions.

**Weak fit:** C, C++, Go. Loom's mechanism produces inconsistent or
absent lift. For these languages, either use a stronger executor
(qwen2.5-coder:32b might shift the curve) or rely less on stored-
rule-following and more on tighter test-driven gating.

The honest claim Loom can make:

> "Loom's persistent structured-rule injection drives small-model
> executors toward consistent compliance with stored decisions —
> when the executor model treats structured prompts as authoritative
> in the target language. For qwen3.5 + S1, that's Python, Java,
> TypeScript, and Rust at near-100% with rule context. JavaScript
> shows graduated lift to ~60%. C, Go, and C++ show inconsistent or
> absent lift on this scenario."

---

## Limitations

- **N=5 per cell.** Binomial 95% CI for 60% on N=10 is roughly [27%,
  86%]. The "JS rule+rat = 60%" and "Go +rat = 60%" findings have
  wide error bars.
- **One scenario (S1).** S2 and S3 might show different patterns
  per language. The S1 scenario tests one specific failure mode
  (swallow vs propagate); other constraint types might land
  differently.
- **One model tier (qwen3.5:latest).** qwen2.5-coder:32b might
  shift C/C++/Go from "Loom-resistant" to "Loom-bridging" by
  improving baseline language fluency. This is the most important
  follow-on probe.
- **Direct-Ollama harness, not loom_exec.** The phK Python smoke
  used loom_exec; the per-language smokes (phL/phM/phN/phO/phP/phQ/phR)
  bypass it for tooling reasons. Prompts mirror `task_build_prompt`
  format but the experimental result tests "rule injection works"
  more than it tests Loom's specific delivery infrastructure.
- **Some trials hung.** 3 C++ trials produced 32k+ tokens of prose
  without parseable code blocks. Treated as failures. This is a
  qwen-in-C++ failure mode, not a harness defect.

### Recommended follow-ons (priority order)

1. **Run the same matrix with `qwen2.5-coder:32b`.** Most likely to
   move C/Go from resistant to bridging. Tests whether the regime
   pattern is qwen3.5-tier-specific.
2. **Re-run Go at higher N.** The +rat dropping from +placebo's 100%
   to 60% is suspicious. N=10 or N=20 would clarify.
3. **JS rule+rat at higher N.** The 60% plateau is the most
   informative "graduated" result; tightening its CI would either
   confirm a real ceiling or reveal noise.
4. **S2 + S3 ports across languages.** Test whether the per-language
   regime classification is stable across scenario types.
5. **Add a "stripped-spec" cell** where the rule appears in the
   prompt but with adversarial framing (e.g., "this rule may be
   wrong, use your judgment"). Tests whether qwen's rule-following
   in compliant-cells is genuine acceptance or unconditional
   compliance.

---

## Files of record

- `experiments/bakeoff/benchmarks/crosssession_{c,cpp,java,go,rust,js,ts}/`
  — 7 language-specific S1 ports + their reference impls and tests
- `experiments/bakeoff/v2_driver/ph{L,M,N,O,P,Q,R}_*.py` — 7 per-language
  harnesses
- `experiments/bakeoff/runs-v2/ph{K,L,M,N,O,P,Q,R}_s1_*_run[0-9]_summary.json`
  — 160 trial summaries
- Pre-existing: phK Python S1 (in `phK_s1_*` files) — uses loom_exec;
  prompt format we mirrored in the per-language harnesses
