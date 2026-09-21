# Touchstone · Anti-Hallucination Engineering Kit

> **A touchstone** is a black siliceous stone used to test gold and silver:
> you streak the metal on it and read the colour of the mark.
> It produces no gold of its own and "believes" no metal — it is simply the
> **standard that makes authenticity visible**.

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![CI](https://github.com/cndoin/touchstone/actions/workflows/ci.yml/badge.svg)](https://github.com/cndoin/touchstone/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/cndoin/touchstone)](https://github.com/cndoin/touchstone/releases)
![Zero dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)

Python 3.8+ · **Zero third-party dependencies** · MIT · Offline capable

A hallucination is not "being wrong". It is **asserting confidently without the right to be confident** (ICML 2026, arXiv 2605.01428). The goal is not 100% correct output — that is statistically impossible (arXiv 2509.04664) — but four things:

1. Every factual claim is **traceable** — cite it or delete it
2. Uncertainty must be **downgraded** — never fake certainty
3. **Never claim work you did not do** — execution claims go through the same gate
4. In large projects, **"I remember" is not evidence** — read the actual state first

**What makes it different:** every check a machine can decide is a **script**, not a sentence. Scripts fail closed.

> 中文版见 [README.md](README.md)。

---

## When NOT to use it (v4.1 entry gate)

**This kit is not on by default.** It is a heavyweight pipeline (8 steps + isolated verification +
script gates). Applied to small tasks it only adds latency and burns tokens, buying zero correctness.

**Four-question checklist — any "yes" means engage; all four "yes" means skip the kit:**

| # | Question | What "yes" looks like |
|---|---|---|
| **G1** | Is the change confined to **≤1 file**, the answer a single point, with no external material needed? | Tweak a config value, adjust CSS, rename a variable, explain a function, small single-file refactor |
| **G2** | Does it involve **zero externally decidable facts**? (URL · DOI · paper · legal clause · API · version · package name · path · command output) | Creative copy, chit-chat, formatting |
| **G3** | Is it **reversible**, not entering version history, not conflicting with prior decisions? | Local draft, throwaway script, experimental edit |
| **G4** | Is it **not published externally**, not entering anyone's decision chain? | Internal memo, personal tool, exploratory question |

**All four "yes" → shallow mode: do not load the kit, just answer.**

Not loading it does not mean no floor. Two rules always apply (habits, not process):
**① never cross the red lines** (no fabricated URLs/DOIs/APIs/versions/package names);
**② downgrade when uncertain** (saying "I'm not sure" is correct behavior).

**You MUST engage anyway when:** the user explicitly asks for verification · the output will be adopted
as-is or published · the action is irreversible · the user stated a position and you are about to agree ·
you catch yourself wanting to say "should be / generally".

---

## Math mode (v4.2: numeric conclusions are not computed in your head)

**Mathematical hallucination is different from ordinary factual hallucination — at least half of it is decidable.**
Whether arithmetic is right and whether a proof is valid can be machine-checked, so that half can be
driven close to zero. But the errors sit in different layers, and **the treatments do not transfer between them**.

| Layer | Symptom | Treatment | Status |
|---|---|---|---|
| ① Arithmetic / symbolic slip | `3×7=20`, sign error when transposing | **Force a deterministic engine** (Python / SymPy / Z3) | Solved |
| ② **Executable but ungrounded** | Formula right, units right, **wrong variable** | **Two-layer check**: symbolic validity + semantic groundedness | Research frontier |
| ③ Ill-posed / under-specified | A missing premise, self-contradictory, outside the domain | **Abstain / clarify gate** (decide *before* answering) | **Hardest** |
| ④ The verifier itself is untrustworthy | Rule-based misses equivalent formats; model-based gets gamed | **De-anchor**: the judge commits its own answer first | Clear fix exists |

**Four hard clauses:**

1. **A numeric conclusion must carry an execution record** — from an actually-run `python3 -c "…"` or SymPy, never "I believe".
2. **Tool success ≠ correct math.** Running clean only proves the syntax is valid. The second layer must ask
   **"Which word in the problem statement does this variable refer to?"** — if you cannot point to it, the step is ungrounded; downgrade it.
3. **Decide whether the premises are complete before answering**: missing ⇒ ask first; if asking is impossible, **condition the answer**
   ("if X = … then …"); abstain only last. **Never silently invent a value to fill the gap.**
4. **When checking an answer, the judge commits its own answer first** (Iron Rule 2 in the math domain). Reversing the order
   zeroes out the chain: seeing the candidate first pushes the false-positive rate from 0.012 back to 0.719.

> ⚠ Layer ③ **does not improve with a stronger model, nor with more thinking time** —
> on the Soohak refusal subset **no model exceeds 50%** (arXiv 2605.09063).
> So do not use "check it again more carefully" as a gate. See `references/18-math-mode.md`.

---

## Quick start

```bash
# 0) Model capability tiering: different model strengths need different verification strategies
python3 scripts/model_profile.py --model claude-opus-4 --net on

# 1) Hard checks: URL / DOI / file / command / package version (not found = does not exist)
python3 scripts/hardcheck.py --file ./README.md --cmd "git status --porcelain" --offline

# 2) Delivery gate (non-zero exit = do not deliver)
python3 scripts/claim_lint.py --input examples/claims-good.json

# 3) Dependency & symbol hallucination guard (phantom imports / package hallucination / slopsquatting)
python3 scripts/dep_guard.py --root . --offline

# 4) Project ledger: record decisions / detect drift
python3 scripts/ledger.py add --kind decision --subject "DI framework" --value "Hilt"
python3 scripts/ledger.py check --root . --drift

# 5) One-command pipeline: hardcheck → dep_guard → claim_lint
python3 scripts/pipeline.py --root . --checks checks.json --claims claims.json --level L1

# 6) Self-tests
python3 scripts/selftest.py           # 72 smoke cases (seconds)
python3 scripts/robustness_test.py    # 70 deep cases (boundary/anomaly/concurrency/perf)
python3 scripts/stability_test.py     # 99 engineering-consistency cases (97 with --no-install-check)
python3 scripts/audit.py              # open-source compliance audit
```

On Windows use `python` instead of `python3`. Only the Python standard library is required.

> **Your first run may exit non-zero — that is not necessarily a failure.** Read this first:
>
> | Command | Common non-zero exit | Meaning |
> |---|---|---|
> | `selfcheck.py` | **2** | Gray zone (consistency landed in the middle band). This is a **routing signal** — "go retrieve or verify in isolation", not a failure |
> | `hardcheck.py --offline` | **2** | Offline, external URLs/packages can only be recorded as unverified. **Unverified ≠ pass**, and ≠ fail |
> | `dep_guard.py --offline` | **2** | Same: no registry access offline, so external packages become UNVERIFIED |
> | `claim_lint.py` | **1 / 2** | 1 = genuinely failed (do not deliver); 2 = has unverified items |
>
> Full semantics under "Exit codes" below. **When in doubt, treat 2 as "a human must check this", never as a pass.**

---

## Why not just "please double-check"?

Because advice can be skipped. A script cannot.

| Prose instruction | Executable gate |
|---|---|
| "Make sure sources are real" | `hardcheck.py` actually requests every URL |
| "Don't invent packages" | `dep_guard.py` queries npm / PyPI and flags packages first published < 90 days ago |
| "Verify before saying done" | `claim_lint.py` rejects `verified: true` without evidence text |
| "Be honest about uncertainty" | `selfcheck.py` measures sampling consistency and forces a label |
| "Remember project conventions" | `ledger.py` stores them on disk and detects drift against reality |

---

## Repository layout

```
touchstone/
├── SKILL.md                      Main entry (rules, workflow, routing)
├── i18n/en/SKILL.md              English main entry
├── LICENSE · NOTICE · CONTRIBUTING.md · SECURITY.md · CITATION.cff · VERSION
├── README.md (中文) · README.en.md (English) · CHANGELOG.md · ATTRIBUTIONS.md
├── references/                   17 deep references
├── scripts/
│   ├── hardcheck.py              URL / DOI / file / command / PyPI / npm
│   ├── dep_guard.py              Phantom imports, package hallucination, slopsquatting
│   ├── claim_lint.py             Output contract gate (logic, not just format)
│   ├── ledger.py                 Project ledger + drift detection
│   ├── pipeline.py               One-command orchestration
│   ├── selfcheck.py              Sampling consistency (fallback when nothing to check against)
│   ├── regression.py             Hallucination regression suite
│   ├── selftest.py               72 smoke cases
│   ├── robustness_test.py        70 deep cases
│   ├── stability_test.py         99 engineering-consistency cases
│   └── audit.py                  Open-source compliance audit
├── assets/                       Schemas, templates, regression cases, CI example
├── examples/                     Runnable examples (including one deliberately wrong)
└── adapters/
    ├── claude-code/              Stop / SubagentStop / PreCompact / PreToolUse hooks
    ├── deepseek/                 System prompt + reasoning-model guidance
    └── generic/                  Codex / Cursor / Cline / Roo / custom agents
```

---

## Install

```bash
# 1) Get the code
git clone https://github.com/cndoin/touchstone.git
cd touchstone

# Verify once — no dependencies to install (standard library only, Python 3.8+)
python scripts/selftest.py     # use `python` on Windows; expects 38/38

# 2) Drop it into your agent
# WorkBuddy / generic skill dir
cp -r touchstone ~/.workbuddy/skills/

# Claude Code (strongest enforcement — hooks are deterministic)
cp -r touchstone .claude/skills/
# then merge adapters/claude-code/settings-hooks.json into .claude/settings.json
```

After merging hooks, **trigger a hook once manually**: hooks fail open by design
(a broken hook must never block your work), so a misconfiguration produces no error at all.

Other harnesses: see `adapters/generic/README.md` (AGENTS.md, .cursorrules, .clinerules, GEMINI.md...).

---

## Core mechanisms

| Layer | Mechanism | Origin |
|---|---|---|
| **M0** | **Entry gate (decides whether to engage the kit at all)** | this kit (v4.1) |
| M1 | Context classification (Accurate / Noisy / Zero) | RefChecker |
| M2 | Behavioral baseline (escape hatch, red lines, calibrated language) | Anthropic + OpenAI 2509.04664 + ICML 2605.01428 |
| M3 | Hard checks on decidable items | Microsoft refchecker + FacTool |
| M4 | 8-step workflow with context-isolated verification | FacTool + CoVe |
| M5 | Labels / confidence / counterexamples | verify-gate + Cleanlab TLM |
| M6 | Cost routing (cheap first, escalate on gray zone) | HalluScan ADR |
| **M7** | **Math mode (forced deterministic engine + semantic groundedness + ill-posed gate)** | **this kit (v4.2); theory from Neuro-symbolic PRM 2608.26329 / Soohak 2605.09063 / 2607.05904** |

Plus two layers this kit adds: **large-project mechanics** (ledger + drift) and **executable gates**.

---

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Pass |
| 1 | Failed (**do not deliver**) |
| 2 | Unverified (network failure etc.) — **unverified ≠ pass** |
| 3 | Usage / input error (argparse errors are normalized to 3 so they never collide with "unverified") |

`selfcheck.py` uses codes as routing signals: `0` high consistency, `2` gray zone, `4` low, `3` error.

---

## Testing

| | `selftest.py` | `robustness_test.py` | `stability_test.py` |
|---|---|---|---|
| Role | Fast smoke | Deep robustness | Engineering consistency |
| Cases | 72 | 70 | 99 (97 with `--no-install-check`) |
| Covers | Happy path + key failure paths | Boundaries, anomalies, encodings, concurrency, performance, idempotency | Compilation, idempotency, concurrent writes, fuzz, environment (GBK / offline / read-only / non-ASCII paths), doc & version consistency, asset validity, install-dir sync |
| Runtime | seconds | tens of seconds | minutes (includes 16-way concurrency and 200KB inputs) |
| Run it | after every change | before release, after environment change | before release (especially after touching hooks, docs, or the version number) |

The first two answer "do the scripts behave correctly". The third answers
"**has the whole skill package rotted**" — a hook with a syntax error, a version number
in the docs that disagrees with `VERSION`, a documented file that does not exist,
or a workspace that was never synced to the install directory.

> Group G of `stability_test.py` byte-compares the workspace against the installed skill
> directory, so it only means something when the skill is actually installed locally.
> In CI or a fresh clone it degrades to 97 cases automatically (group G skipped) —
> pass `--no-install-check` to skip it explicitly, or set
> `TOUCHSTONE_INSTALLED=/path/to/skill` if you installed it elsewhere.
> **99 is the full local number; 97 does not mean tests went missing.**

`audit.py` is the fourth gate: open-source compliance (license headers, zero third-party
dependencies, no leaked local paths or emails, version consistency).

`robustness_test.py` asserts things that matter more than correctness:
**no Traceback ever**, exit code within {0,1,2,3}, `--json` parseable, idempotent across runs,
and performance budgets (200 files < 5s, 1000 claims < 10s).

Nasty inputs covered: GBK files, UTF-8 BOM, empty files, >2MB files, binaries, paths with CJK and spaces,
50-level nested dirs, `node_modules`, corrupt JSON, contracts with wrong field types,
5 processes writing the same cache dir, corrupted cache files, `--timeout 0`,
`--max-checks -1`, `--jobs -5`, 50k-char commands, emoji, and 20 malformed hook inputs.

Current status: **38/38, 70/70, and 99/99 passing**, `audit.py` clean.

---

## Metrics to track

| Metric | Target |
|---|---|
| Unsourced claim rate | → 0 |
| Unverified execution claims | → 0 |
| Resolvable citation rate | → 100% |
| Abstention rate | 5–20% (too low = the model is guessing) |

---

## Why "Touchstone"

A touchstone is a black siliceous stone used to assay gold and silver — you streak
the metal across it and judge purity by the colour of the mark left behind.

That is exactly this kit's stance:

- **It does not decide truth for the model.** Asking a model to "double-check" is
  actively harmful on weaker models (arXiv 2601.00513, d = −0.14 to −0.33) —
  self-critique is not a reliable judge. See `references/16-model-adaptation.md`.
- **It only provides executable standards.** Found = sourced; not found = does not
  hold. Anything a machine can decide is a script, never a sentence like
  "please verify carefully".
- **When it cannot decide, it says `unverified`.** Unverified ≠ pass. That single
  rule is the floor the whole kit stands on.

> **Formerly named `dehallucination`.** The rename is for readability;
> `dehallucination` is kept as a keyword and search alias, and GitHub redirects
> the old repository URL automatically.

---

## Contributing

- Bug reports / feature requests: GitHub Issues (templates provided; blank issues are disabled).
- Pull requests: read `CONTRIBUTING.md` and fill in the PR template — **evidence of verification is mandatory**.
  Three hard rules: no third-party dependencies, every factual claim must cite a primary or
  secondary source, and any script change ships with tests.
- Security issues: `SECURITY.md` → GitHub Security Advisory (private, never a public issue).
- Conduct: `CODE_OF_CONDUCT.md`. Releasing: `RELEASE.md`. Maintainers: `MAINTAINERS.md`.

> One extra rule for contributors: **do not put fabricated numbers, fabricated paper IDs,
> or over-generalized conclusions into this repo's docs.** An anti-hallucination repo that
> tolerates hallucination has no value — so this is enforced as a code-of-conduct matter,
> not just a style preference.

---

## License & attribution

- **MIT** — see `LICENSE`. No third-party source code is included; see `NOTICE`.
- Methods and their sources (papers, projects, licenses, primary/secondary tagging): `ATTRIBUTIONS.md`.
- Academic citation: `CITATION.cff`.

**No warranty.** This kit reduces hallucination risk; it does not eliminate it.
Keep a human in the loop for legal, medical, financial, and irreversible operations.
