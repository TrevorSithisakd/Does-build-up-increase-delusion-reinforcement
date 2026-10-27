# Research log

## 2026-10-27 (Claude Code, cloud session)

- **Last:** Built T1, T2, T4–T8 plus `sample_for_labels.py` and `analyse.py`. Full pipeline runs end to end on the mock client (`--dry-run`), 26 tests pass. Rubric copied verbatim from `MrinankSharma/disempowerment-prompts@dd36c1c` (`schemas.py`, `REALITY_DISTORTION_PRIMITIVE_SCHEMA`), verified by string comparison. Cost cap made cumulative across runs per results dir. Parallel calls (`workers` in config) added so the full run is minutes, not hours.
- **Next:** Trevor fills `config.yaml` model IDs and prices from openrouter.ai/models, adds `.env`, writes the 2 pilot beliefs in `data/scenarios_draft.jsonl` (T3), then runs the pilot (T9).
- **Blockers:** Pilot beliefs (Trevor). Model IDs (Trevor). Decide before the freeze: poscontrol "low" threshold (analyse.py warns below 50%, a placeholder) — goes in PREREGISTRATION.md.
- **Cost note:** the grader prompt is ~4k tokens (the full schema), so 1,200 grades at a $3/M-input grader is ~$15. With replies, total can approach the $25 cap; pick the grader with that in mind or raise the cap deliberately.

## 2026-10-27, later (Claude Code, cloud session)

- **Last:** Pipeline merged to `main` and pushed. Discussed grader and reference-model choice: grader = Opus 4.5 (the model Sharma et al. validated the schema with, App. B: 74.3% exact / 96.3% within one; Sonnet 4.5 75.7% / 90.3% as the cheaper fallback). Reference model = a fourth family, not one of the 3 tested.
- **Next:** Trevor picks the 5 model IDs; raise `cost_cap_usd` deliberately if the grader is Opus-priced.
- **Blockers:** none new.
- **Limitation candidates for the README** (notes only; Trevor writes the prose and decides which stay):
  - Self-preference: a Claude grader scoring a Claude model's replies. LLM judges can favour their own family. Mitigated by keeping the tested Anthropic model different and smaller, and by the human labels.
  - Grader validated on whole conversations in the paper, applied here to a single final reply, so the paper's agreement numbers don't transfer; only our own κ does.
  - Human labels: one rater (Trevor), 40 items, blind to condition but not to the hypothesis.
  - Blind grading trades context for unbiasedness: a reply that is harmless alone but validating in context ("yes, like you said") can be under-scored.
  - Prefilled neutral assistant turns isolate the user build-up, so the result likely underestimates real spirals, where the model's own earlier validation compounds.
  - Buildup escalates emotion as well as belief; neutral holds rung-1 tone. An effect could come from emotional intensity, not belief drift.
  - 6 turns, vs the 30–50+ exchange spirals in the paper's clusters. One dose (buildup3 optional).
  - n = 20 beliefs written by one author, not clinically reviewed; synthetic, English only. Small n plus Holm across 9 tests means only large effects are detectable.
  - 3 models, one snapshot each, via OpenRouter routing (`served_model` logged). Floor effects possible if frontier models rarely validate cold.
  - Binary threshold (score >= 2) puts weight on the 1-vs-2 boundary.
