# Research log

## 2026-10-27 (Claude Code, cloud session)

- **Last:** Built T1, T2, T4–T8 plus `sample_for_labels.py` and `analyse.py`. Full pipeline runs end to end on the mock client (`--dry-run`), 26 tests pass. Rubric copied verbatim from `MrinankSharma/disempowerment-prompts@dd36c1c` (`schemas.py`, `REALITY_DISTORTION_PRIMITIVE_SCHEMA`), verified by string comparison. Cost cap made cumulative across runs per results dir. Parallel calls (`workers` in config) added so the full run is minutes, not hours.
- **Next:** Trevor fills `config.yaml` model IDs and prices from openrouter.ai/models, adds `.env`, writes the 2 pilot beliefs in `data/scenarios_draft.jsonl` (T3), then runs the pilot (T9).
- **Blockers:** Pilot beliefs (Trevor). Model IDs (Trevor). Decide before the freeze: poscontrol "low" threshold (analyse.py warns below 50%, a placeholder) — goes in PREREGISTRATION.md.
- **Cost note:** the grader prompt is ~4k tokens (the full schema), so 1,200 grades at a $3/M-input grader is ~$15. With replies, total can approach the $25 cap; pick the grader with that in mind or raise the cap deliberately.
