"""Blind check that neutral conversations carry no hint of the belief (and buildup ones do).

    python -m src.check_neutrality                  # data/scenarios_draft.jsonl
    python -m src.check_neutrality --only grand-01
    python -m src.check_neutrality --dry-run        # mock model, dummy scenarios

The checker sees only the 6 user turns of one conversation: no final message, no condition,
no theme. Expected: neutral -> 0 (no hint), buildup -> 1 (hint). Uses the grader model at
temperature 0. Writes results/neutrality_check.jsonl, overwritten each run.
"""
import argparse

from .client import make_client
from .common import CONTEXT_CONDS, ROOT, append_jsonl, load_config, load_scenarios, out_dir, parse_only
from .grade import parse_grade

EXPECTED = {"buildup": 1, "neutral": 0}


def build_prompt(template, user_turns):
    turns = "\n".join(f"[{i}] {u}" for i, u in enumerate(user_turns, 1))
    return template.replace("<<TURNS>>", turns)


def check_one(client, cfg, template, user_turns):
    msgs = [{"role": "user", "content": build_prompt(template, user_turns)}]
    r = client.chat(cfg["grader_model"]["id"], msgs, temperature=0, max_tokens=150)
    g = parse_grade(r["text"])
    hint = None if g is None else int(g["score"] >= 1)
    return hint, (g["reason"] if g else f"UNPARSEABLE: {r['text'][:120]}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--only")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)

    cfg = load_config()
    inp = a.inp or ROOT / "data" / ("scenarios_dummy.jsonl" if a.dry_run else "scenarios_draft.jsonl")
    out = out_dir(a.dry_run) / "neutrality_check.jsonl"
    if out.exists():
        out.unlink()

    template = (ROOT / "prompts" / "neutrality_check.md").read_text(encoding="utf-8")
    client = make_client(cfg, a.dry_run)
    scen = load_scenarios(inp, require_assistant=False, only=parse_only(a.only))

    bad = 0
    for s in scen:
        for cond in CONTEXT_CONDS:
            hint, reason = check_one(client, cfg, template, s[cond]["user"])
            ok = hint == EXPECTED[cond]
            bad += not ok
            append_jsonl(out, {"id": s["id"], "cond": cond, "hint": hint, "ok": ok, "reason": reason})
            print(f"{'ok  ' if ok else 'FAIL'} {s['id']:<12} {cond:<8} hint={hint}  {reason}")

    print(f"\n{len(scen) * len(CONTEXT_CONDS) - bad}/{len(scen) * len(CONTEXT_CONDS)} as expected"
          f" -> {out}  |  spend ${client.tracker.spent:.4f}")
    if bad:
        print("FAIL on neutral: rewrite it so it hints at nothing. FAIL on buildup: the ladder may be too subtle.")


if __name__ == "__main__":
    main()
