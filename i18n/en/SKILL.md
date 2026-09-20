---
name: touchstone
description: Touchstone · anti-hallucination engineering kit (a touchstone is a stone for assaying gold; formerly named dehallucination). **Use ONLY when at least one of these holds:** (1) the output must cite externally decidable facts — URLs, DOIs, papers, legal clauses, API signatures, version numbers, package names, file paths, command output; (2) the domain is high-stakes or irreversible — legal, medical, financial, public release, production operations; (3) it is a large long-running project — multi-session, huge codebase, many subagents — where errors compound; (4) the user explicitly asks for verification — "does this really exist", "verify this", "don't make things up", "is this API/paper/file real", "are you sure it's finished"; (5) the output will be adopted without human review, or the user has stated a position and sycophancy is a risk. **Do NOT load this kit for:** chit-chat, creative writing, formatting tweaks, small single-file edits, small local refactors that run locally, explaining code, or one-off quick questions — these have no externally decidable facts, are reversible and internal; just answer directly. Loading the kit only slows things down and burns tokens.
license: MIT
version: 4.1.0
---

# Touchstone · Anti-Hallucination Engineering Kit

**A hallucination is not "being wrong". It is "asserting confidently without the right to be confident."** (ICML 2026, arXiv 2605.01428)

The goal is not 100% correct output — that is statistically impossible (arXiv 2509.04664). The goal is five things:

1. **Every factual claim is traceable** — cite it, or delete it
2. **Uncertainty must be downgraded** — never fake certainty
3. **Never claim work you did not do** — execution claims go through the same gate
4. **In large projects, "I remember" is not evidence** — read the actual state first
5. **The user's stance never enters the evidence chain** — agreeing with the user is the hardest hallucination to self-detect

> v3.4 adds a failure mode the earlier layers miss: **the model knows the right answer and changes it
> because the user stated a position first** (sycophancy-induced hallucination, *Science* 2026).
> See Iron Rule 9 and `references/17-vendor-and-induction.md`.

What makes v3 different: **every check that a machine can decide is a script**, not a sentence. Scripts fail closed.

---

## Entry gate (answer this FIRST — it decides whether the kit is used at all)

**This kit is not on by default.** It is an expensive heavyweight pipeline (8 steps + isolated
verification + script gates). Applying it to small tasks only adds latency and burns tokens,
while buying zero correctness.

### Four-question checklist (any "yes" → engage; all four "no" → do not load, just answer)

| # | Question | What "yes" looks like |
|---|---|---|
| **G1** | Is the change confined to **≤1 file**, the answer a **single point**, with no external material needed? | Tweak a config value, adjust CSS, rename a variable, explain a function, small single-file refactor |
| **G2** | Does it involve **zero externally decidable facts**? (URL · DOI · paper · legal clause · API signature · version · package name · file path · command output) | Creative copy, chit-chat, formatting |
| **G3** | Is it **reversible**, not entering version history, not conflicting with prior decisions? | Local draft, throwaway script, experimental edit |
| **G4** | Is it **not published externally**, not entering anyone's decision chain, harmless if wrong? | Internal memo, personal tool, exploratory question |

**All four "yes" → shallow mode: do not read the rest of this kit, answer directly.**

### What still holds in shallow mode (minimum floor, ~zero cost)

Not loading the kit does not mean no floor. These two always apply, because they are **habits**, not **process**:

1. **Never cross the red lines** — do not fabricate URLs / DOIs / papers / legal clauses / APIs / versions / package names / file paths / command output. If you need a citation and aren't sure, say "I need to verify this" — never invent something plausible.
2. **Downgrade when uncertain** — say "I don't know" when you don't. That is correct behavior, not failure.

### When you MUST escalate to engaging the kit (any hit → engage, however small the task looks)

- Any of G1–G4 is "no"
- The task is small but the **user explicitly asks for verification**: "does this really exist", "verify this", "don't make things up" (an explicit request = mandatory engagement)
- The output will be **adopted as-is or published** (even a single sentence)
- It involves an **irreversible action** (deleting data, changing production config, releasing, external commitments)
- **The user has stated a position** and you are about to agree (anti-sycophancy, see Iron Rule 9)
- You catch yourself wanting to say "should be", "generally", "most likely" — that is the signal of "asserting without the right to be confident". Engage.

> When in doubt, engage: engaging costs some tokens, while skipping the gate can push a fabrication into
> someone's decision. But the **default is not to engage** — most everyday requests are small tasks.

---

## 0. Four questions at task start

```
Q0 Model tier?  → scripts/model_profile.py → S/A may self-verify; B/C must use external scripts
Q1 Context?     Accurate (single authoritative source) / Noisy (RAG, multi-doc) / Zero (no material — must retrieve)
Q2 Risk?        L0 chat & drafts / L1 business, coding, reports / L2 legal, medical, finance, publishing, irreversible
Q3 Decidable?   URL / DOI / file / command / version / package → run scripts/hardcheck.py, never rely on memory
```

Cannot answer Q1 → treat as **Noisy** (safe default). Cannot answer Q3 → the item is undecidable; do not assert facts about it.

**Q0 decides the play (critical):** strong models (S/A) can be asked to self-verify in isolation;
weak models (B/C) **cannot self-verify reliably** — they cannot tell whether they were wrong, so asking them to
"check again" only re-confirms the wrong answer. Weak models must delegate the decision to scripts.
See `references/16-model-adaptation.md`.

---

## Nine Iron Rules

1. **No source = delete it.** Remove the claim and leave `[]` in place. Do not polish it away, do not fill the gap with plausible inference.
2. **Verification must be isolated.** Never put the draft into the verification subtask — the model anchors on its own output (CoVe, arXiv 2309.11495). This is what makes the whole pipeline work.
3. **Falsify first, confirm second.** Actively look for counter-evidence before upgrading to `confirmed`.
4. **"Done" is also a claim.** Does the file exist? Did tests actually run? No verification, no claim.
5. **Check the decidable first.** URL / DOI / entity / API / file / version / command output — these are 100% checkable and nearly free. Do not burn budget on vague assertions.
6. **In large projects, memory is not evidence.** Statements about codebase state must come from files or tool output read **in this session**.
7. **Tool failure ≠ pass.** Empty retrieval, script error, timeout, silent subagent → record `unverified`. Never default to pass.
8. **Dependencies must resolve.** Check the registry before adding a package (does it exist? how old? repo link?). Hallucinated package names get squatted — one `npm install` becomes a supply-chain incident (slopsquatting).
9. **The user's stance must not enter the evidence chain.** Before verifying, **restate the question neutrally** (strip "I think / surely / isn't it true that") and hand only the neutral form to the verifier. Models that know the right answer still switch sides when the user states a position — hard evidence below. **Same source = not independent:** if several samples or agents say the same thing, check whether they shared a source; if so it counts as ONE piece of evidence.
   - *Science* 391(6792), DOI 10.1126/science.aec8352 — 11 models affirmed user behavior **49% more** than humans did. The very feature that causes the harm is what drives engagement.
   - arXiv 2602.19141 — even an ideal Bayesian user is vulnerable; two candidate mitigations (banning fabrication, warning users) both **fail**.
   - Consequences: at minimum rewrite neutrally, then verify in isolation. A prompt saying "don't be sycophantic" does nothing.

---

## Red Lines (never generate without verification)

URL · DOI · paper title & authors · legal clauses · statistics · API names & parameters · file paths · command output · version numbers · names & titles · dates · prices · dependency coordinates · config keys · DB column names · **package names & import paths**

---

## Workflow (8 steps + 1 gate)

```
[0] Classify context   Accurate / Noisy / Zero
[1] Draft              Normal output, allowed to be imperfect
[2] Atomize            Split into atomic claims; use (subject, relation, object) triples
[3] Hard checks        Run scripts/hardcheck.py on every decidable item
[4] Plan verification  Write a question that could FALSIFY each claim
[4.5]Restate neutrally Strip the user's stance and wording; hand only the neutral form over  ← anti-sycophancy
[5] Verify in isolation Subtask/subagent without the draft  ← the critical step
                 ⚠️ Even "they all agree" is not confirmation: check for a shared source first, then see the ceiling below
[6] Score & label      confirmed/observed/assumed/hearsay/unknown + confidence + alternative
[7] Revise             contradicted → fix or delete; unverified → downgrade or delete with []
[8] Execution gate     "done" claims get ls / test output / command receipts
[gate] claim_lint.py   Non-zero exit = do not deliver
```

**Cost routing** (HalluScan ADR: 2.0× cheaper, AUROC −0.1%):

```
Cheap (default) → hard checks / NLI / sampling consistency
     ↓ gray zone
Medium          → targeted retrieval + cross-checking
     ↓ still unsure
Expensive       → LLM-as-judge / multi-model (10–100× costlier)
```

**Self-consistency ceiling (v3.4 correction):** among answers where all 8 samples agree, **15–23% are still wrong**
(arXiv 2607.11414, FinQA). A high-consistency `selfcheck.py` result is a **passing line, not a confirmation**;
upgrading to `confirmed` still requires ≥2 independent primary sources.

---

## Large projects (multi-session, huge codebase, many subagents)

Hallucination in big projects is **cumulative**: a wrong statement on day 3 becomes "established fact" on day 30.

| Mechanism | Tool |
|---|---|
| Read before you speak | — |
| Decision ledger on disk (architecture, contracts, conventions) | `scripts/ledger.py` |
| Drift detection: ledger vs reality | `scripts/ledger.py check --drift` |
| Subagent reports are hearsay until independently verified | same as step 8 |
| Milestone gates | `scripts/pipeline.py` |
| Quote-first for long docs (>20k tokens) | Anthropic's approach |

---

## Risk tiers

| Tier | Scope | Investment |
|---|---|---|
| L0 | Chat, brainstorming, internal drafts, small single-file edits | Baseline rules + red lines; **shallow mode — do not load the kit** (see Entry gate) |
| L1 | Business, coding, research, reports | + hard checks + 8-step workflow |
| L2 | Legal / medical / finance / publishing / irreversible | + mandatory retrieval + multi-model + human gate |

---

## Calibrated language

| Confidence | How to phrase it |
|---|---|
| High (sourced, counter-checked) | "According to X §2.1, ..." |
| Medium (single source) | "Only one source (X) mentions this; worth cross-checking" |
| Low (inference) | "My leaning is ..., but I'm not confident; verify this" |
| None | "I don't know" / "Not in the material" / "Needs checking" |

**Saying "I don't know" is correct behavior, not failure.** Mainstream benchmarks penalize abstention, which trains models to guess — invert that incentive locally.

Low-confidence claims **must** carry an alternative ("another plausible answer is X"). A counterexample beats a score.

---

## Executable gates (Python 3.8+, standard library only)

```bash
python3 scripts/hardcheck.py --file ./README.md --cmd "git status --porcelain" --offline
python3 scripts/dep_guard.py --root . [--offline] [--strict]
python3 scripts/claim_lint.py --input claims.json --min-level L1
python3 scripts/pipeline.py --root . --checks checks.json --claims claims.json
python3 scripts/ledger.py check --root . --drift
python3 scripts/selftest.py            # 38 smoke cases (seconds)
python3 scripts/robustness_test.py     # 70 deep cases (boundary/anomaly/concurrency/perf)
python3 scripts/stability_test.py      # 99 engineering-consistency cases
python3 scripts/audit.py               # open-source compliance audit
```

Principles: **fail-closed** (failure = unverified, never pass), **zero third-party dependencies**,
**offline capable** (network failure degrades to `unverified`, never crashes).

Exit codes: `0` pass · `1` failed · `2` unverified · `3` usage/input error
(`selfcheck.py` uses codes as routing signals: 0 high / 2 gray / 4 low / 3 error).

---

## Anti-patterns

| Don't | Why |
|---|---|
| "Re-check" in the same context | No isolation = anchored on your own draft |
| Trust a self-reported "verified" | Self-report is not evidence |
| Tune temperature against hallucination | Empirically negligible effect |
| Endlessly lengthen the prompt | Long prompts increase errors (~10%) |
| Trust CoT / long reasoning | CoT can raise hallucination ~12% on complex tasks |
| Use whatever retrieval returns | RAG fails silently → plausible-sounding fakes |
| Report accuracy alone | Track error rate AND abstention rate |
| Trust subagent self-reports | Their report is a claim too |
| Answer while agreeing with the user's stance | Sycophancy: the model knows the answer and still switches sides |
| Treat "several samples agree" as evidence | On FinQA, 15–23% of 8/8-agreement answers are still wrong; and shared source = not independent |
| Write "be careful not to be sycophantic" in the prompt | First-party evidence: self-reminders and user warnings both fail. Restate neutrally + isolate |
| Ask a small model to "reflect on it" | Empirically harmful (d = −0.14 to −0.33). Give it evidence instead |
| Use second-hand numbers as facts | Trace to the primary source or mark unknown |

---

## References (load on demand, not all at once)

| File | Content |
|---|---|
| `references/01-core-doctrine.md` | Why hallucination is unavoidable, and what is left to do |
| `references/02-context-settings.md` | Accurate / Noisy / Zero |
| `references/03-hard-checks.md` | Decidable items + script usage |
| `references/04-verification-workflow.md` | 8 steps + isolation templates |
| `references/05-claim-labels.md` | Five labels, confidence tiers, phrasing |
| `references/06-cost-routing.md` | Detector selection + ADR routing |
| `references/07-large-project.md` | Ledger, drift, cross-session, subagents |
| `references/08-code-mode.md` | Phantom APIs, versions, build verification |
| `references/09-anti-patterns.md` | Anti-patterns + pre-delivery checklist |
| `references/10-metrics-regression.md` | Metrics + regression suite |
| `references/11-harness-adapters.md` | Claude Code / DeepSeek / generic harnesses |
| `references/12-uncertainty-calibration.md` | Semantic entropy, self-consistency, calibration |
| `references/13-frontier-2026.md` | 2026 papers & ecosystem (credibility-tagged) |
| `references/14-supply-chain-code.md` | Package hallucination / slopsquatting |
| `references/15-stability-performance.md` | Environment matrix, caching, budgeting, crash discipline |
| `references/16-model-adaptation.md` | Model tiers: strong models self-check, weak models use scripts; vendor mechanisms |
| `references/17-vendor-and-induction.md` | **Vendor official approaches (OpenAI/Anthropic, first-party) + sycophancy-induced hallucination + self-consistency ceiling + detector-permission tiers + per-tier playbook** |

License & attribution: `LICENSE` (MIT) · `NOTICE` · `ATTRIBUTIONS.md` (sources, licenses, primary/secondary tagging) · `CITATION.cff`.
