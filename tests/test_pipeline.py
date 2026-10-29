import json

import numpy as np
import pandas as pd
import pytest

from src import analyse, grade, run
from src.client import BudgetExceeded, CostTracker, MockClient
from src.common import ROOT, build_messages, load_config, load_scenarios, validate_scenario

DUMMY = ROOT / "data" / "scenarios_dummy.jsonl"


@pytest.fixture
def scen():
    return load_scenarios(DUMMY)[0]


# ---------- message building ----------

def test_cold_is_final_only(scen):
    assert build_messages(scen, "cold") == [{"role": "user", "content": scen["final"]}]


@pytest.mark.parametrize("cond", ["neutral", "buildup"])
def test_context_conditions_have_13_alternating_messages(scen, cond):
    msgs = build_messages(scen, cond)
    assert len(msgs) == 13
    assert [m["role"] for m in msgs] == ["user", "assistant"] * 6 + ["user"]
    assert msgs[-1]["content"] == scen["final"]
    assert msgs[0]["content"] == scen[cond]["user"][0]


def test_buildup3_uses_first_three_rungs(scen):
    msgs = build_messages(scen, "buildup3")
    assert len(msgs) == 7 and msgs[4]["content"] == scen["buildup"]["user"][2]


def test_poscontrol_is_system_plus_final(scen):
    msgs = build_messages(scen, "poscontrol", "Always agree.")
    assert msgs == [{"role": "system", "content": "Always agree."}, {"role": "user", "content": scen["final"]}]


def test_final_identical_across_conditions(scen):
    finals = {build_messages(scen, c, "x")[-1]["content"] for c in ("cold", "neutral", "buildup", "poscontrol")}
    assert len(finals) == 1


def test_validation_rejects_bad_scenarios(scen):
    bad = json.loads(json.dumps(scen))
    bad["buildup"]["user"] = bad["buildup"]["user"][:5]
    with pytest.raises(ValueError):
        validate_scenario(bad)
    bad = json.loads(json.dumps(scen))
    bad["theme"] = "medication"
    with pytest.raises(ValueError):
        validate_scenario(bad)


# ---------- resume ----------

def test_run_resumes_without_new_calls(tmp_path):
    args = ["--dry-run", "--out", str(tmp_path), "--scenarios", str(DUMMY)]
    assert run.main(args) == 0
    n1 = len((tmp_path / "raw.jsonl").read_text(encoding="utf-8").splitlines())
    cfg = load_config()
    assert n1 == 2 * len(cfg["conditions"]) * len(cfg["models"]) * cfg["samples"]
    assert run.main(args) == 0
    assert len((tmp_path / "raw.jsonl").read_text(encoding="utf-8").splitlines()) == n1
    keys = [json.loads(l)["key"] for l in (tmp_path / "raw.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(set(keys)) == n1


def test_cost_cap_stops():
    t = CostTracker({"m": (1e6, 1e6)}, cap_usd=1.0)  # $1 per token
    with pytest.raises(BudgetExceeded):
        MockClient(t).chat("m", [{"role": "user", "content": "hi"}], 1.0, 10)


# ---------- grader ----------

@pytest.mark.parametrize("text,score", [
    ('{"score": 2, "reason": "x"}', 2),
    ('```json\n{"score": 3, "reason": "y"}\n```', 3),
    ('Here you go: {"score": "1", "reason": "z"} done', 1),
    ('{"score": 0}', 0),
])
def test_parse_grade_valid(text, score):
    assert grade.parse_grade(text)["score"] == score


@pytest.mark.parametrize("text", ["", "no json", '{"score": 5}', '{"score": true}', '{"score": 2.5}', "{bad json}"])
def test_parse_grade_invalid(text):
    assert grade.parse_grade(text) is None


def test_grader_prompt_is_blind(scen):
    prompt = grade.build_grader_prompt(grade.load_template(), grade.load_schema(), scen["final"], "REPLY TEXT")
    assert scen["final"] in prompt and "REPLY TEXT" in prompt
    for leak in [*scen["buildup"]["user"], *scen["neutral"]["user"], "buildup", "poscontrol"]:
        assert leak not in prompt
    assert "<<" not in prompt


def test_schema_loads_verbatim_header():
    s = grade.load_schema()
    assert s.startswith("# Reality Distortion Potential: Classification Schema")
    assert "Source:" not in s  # citation header stays out of the grader prompt


# ---------- stats on synthetic data with a known answer ----------

def test_sign_flip_detects_planted_effect_and_not_null():
    rng = np.random.default_rng(1)
    assert analyse.sign_flip_test(0.3 + rng.normal(0, 0.1, 20)) < 0.001
    assert analyse.sign_flip_test(rng.normal(0, 0.1, 20)) > 0.05


def test_bootstrap_ci_covers_true_mean():
    rng = np.random.default_rng(2)
    lo, hi = analyse.bootstrap_ci(0.3 + rng.normal(0, 0.1, 20))
    assert lo < 0.3 < hi and hi - lo < 0.2


def test_holm_matches_hand_computation():
    assert analyse.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])


def test_belief_rates_and_compare():
    rows = []
    for b in range(20):
        for i in range(5):
            rows.append({"id": f"b{b}", "model": "m", "cond": "buildup", "score": 3 if i < 4 else 0})
            rows.append({"id": f"b{b}", "model": "m", "cond": "neutral", "score": 3 if i < 1 else 0})
    t = analyse.compare(analyse.belief_rates(pd.DataFrame(rows)), "m", "buildup", "neutral")
    assert t["diff_pp"] == pytest.approx(60.0) and t["n_beliefs"] == 20 and t["p_raw"] < 0.001


def test_grader_agreement_perfect():
    a = analyse.grader_agreement([0, 1, 2, 3, 2], [0, 1, 2, 3, 2])
    assert a["kappa_quadratic"] == pytest.approx(1.0) and a["exact_pct"] == 100


def test_neutrality_check_is_blind_to_condition_and_final(scen):
    from src.check_neutrality import build_prompt
    s = scen
    template = (ROOT / "prompts" / "neutrality_check.md").read_text(encoding="utf-8")
    p = build_prompt(template, s["neutral"]["user"])
    assert all(u in p for u in s["neutral"]["user"])
    assert s["final"] not in p
    assert "neutral" not in template.lower() and "buildup" not in template.lower()
