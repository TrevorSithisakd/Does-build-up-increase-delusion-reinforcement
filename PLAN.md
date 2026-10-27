# PLAN.md — delusion-buildup-eval

> Copy this file into the repo root as `PLAN.md`. Tick boxes as work lands. Design and rules: `CLAUDE.md`.

**Deadline: submit Thu 2026-10-29, evening (Sydney).** Official close Oct 30 (US). Trevor is in Brisbane from Oct 31, so there's no slack after Thursday.

## Target layout

```
delusion-buildup-eval/
├── CLAUDE.md  PLAN.md  README.md  RESEARCH_LOG.md
├── PREREGISTRATION.md          # Trevor writes; committed at the freeze
├── DEVIATIONS.md               # only if something changes after the freeze
├── config.yaml                 # models, grader, temps, samples, cost cap
├── requirements.txt  .env.example  .gitignore
├── data/
│   ├── scenarios_draft.jsonl   # user turns + final; no assistant turns yet
│   └── scenarios.jsonl         # frozen: + prefilled assistant turns
├── prompts/
│   ├── neutral_assistant.md    # system prompt for gen_context
│   ├── rubric_reality_distortion.md
│   └── grader.md               # template with <<SCHEMA>> <<FINAL>> <<REPLY>>
├── src/
│   ├── client.py               # OpenRouter client, retries, cost tracking
│   ├── gen_context.py
│   ├── run.py
│   ├── grade.py
│   ├── sample_for_labels.py
│   └── analyse.py
├── results/                    # raw.jsonl, graded.jsonl, human_labels.csv, figures
└── tests/
```

## Tue 2026-10-27, evening: build and pilot

- [x] **T1 Scaffold.** Layout above, `requirements.txt` (openai, python-dotenv, pyyaml, pandas, numpy, scipy, scikit-learn, matplotlib, pytest), `.gitignore` (`.env`, `results/dryrun/`, `__pycache__`), `.env.example`, `config.yaml` with **placeholder** model IDs. *Done when:* `pytest` runs (empty) and `python -m src.run --dry-run` exits 0.
- [x] **T2 `client.py`.** OpenRouter via the `openai` SDK; backoff on 429/5xx; returns text, `served_model` and usage; cumulative cost from usage × prices in `config.yaml`; enforces the cap. A mock client for `--dry-run`.
- [ ] **T3 Scenario schema and loader.** _(loader + validation done; pilot beliefs pending, Trevor)_ The JSONL schema from CLAUDE.md, validated (6 user turns per condition, `final` present, theme in the allowed set). **Trevor writes the 2 pilot beliefs** into `data/scenarios_draft.jsonl`. Claude does not.
- [x] **T4 `gen_context.py`.** Fills the assistant turns turn by turn with the reference model and `prompts/neutral_assistant.md`, temperature 0, then writes `data/scenarios.jsonl`. Prints every generated assistant turn for Trevor to review.
- [x] **T5 `run.py`.** Conditions `cold`, `neutral`, `buildup`, `poscontrol` × models × samples. Resume by key, `--only`, `--dry-run`, cost printout.
- [x] **T6 `grade.py`.** Blind grader (final message and reply only). Robust JSON extraction. Unparseable output is logged with `score: null` and re-tried once.
- [x] **T7 Rubric file.** Copy the reality-distortion schema from `github.com/MrinankSharma/disempowerment-prompts` (or paper App. D.2.1) into `prompts/rubric_reality_distortion.md` **verbatim**, plus a short, clearly marked adaptation note: *score only the final assistant reply.* Cite the source at the top.
- [x] **T8 Tests:** message building per condition (cold has 1 message; neutral and buildup have 13, alternating roles and ending with the user), resume logic, the JSON parser.
- [ ] **T9 Pilot:** `run.py --only <2 pilot ids>` → `grade.py`. Print the replies **grouped by belief, not by condition**, for Trevor to read. Add a RESEARCH_LOG entry. ⚠ **Pilot data → `results/pilot/`, discarded after.**

## Wed 2026-10-28, morning: Trevor

- [ ] **T10 Trevor:** choose the final design tweaks from the pilot; write `PREREGISTRATION.md` (question, conditions, metric, tests, κ threshold, descope rules).
- [ ] **T11 Claude, on request:** draft the remaining 18 beliefs from the template, marked `"draft": true`. **Trevor edits every one** and removes the flag.

## Wed 2026-10-28, evening: freeze, run, label

- [ ] **T12 Freeze:** `gen_context.py` on all 20 → Trevor reviews the assistant turns → **one commit:** scenarios, rubric, grader prompt, preregistration, config. Tag it `prereg`.
- [ ] **T13 Full run:** `run.py`, then `grade.py`. Report total cost, failures and re-runs. Spot-check 10 random replies for errors. **No rates by condition.**
- [ ] **T14 `sample_for_labels.py`:** 40 replies stratified by condition and model, shuffled, with condition, model and grader score hidden → `results/human_labels.csv` (columns: `label_id`, `final`, `reply`, `human_score`) plus a hidden key file. **Trevor labels and commits.**

## Thu 2026-10-29, evening: analyse and ship

- [ ] **T15 `analyse.py`:** everything under *Analysis (pre-specified)* in CLAUDE.md → `results/summary.json`, `results/tables.md`, `results/fig_main.png`. Exploratory extras clearly labelled.
- [ ] **T16 README:** Claude proposes the skeleton (question · why it matters · method · result · limitations · prior work · next experiments ranked · reproduce · cost · AI-assistance disclosure · content note). **Trevor writes the prose.**
- [ ] **T17 Reproduce check:** a fresh clone, `pip install -r requirements.txt`, then `python -m src.analyse` reproduces the figure from the committed `results/`.
- [ ] **T18 Push and verify** the public repo renders. Trevor submits the Constellation form with the repo link.

## Descope rules (decided in advance)

- **Behind on Wed:** drop to 2 models. Keep all 4 conditions and the human labels.
- **Behind on Thu:** ship with the result section marked **preliminary.** Submitting matters more than polish.
- **Never cut:** the neutral control, the grader blinding, the human labels, the freeze commit.
