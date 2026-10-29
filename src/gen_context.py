"""Fill the prefilled assistant turns (1-6) for buildup and neutral, once, with the reference model.

    python -m src.gen_context                 # data/scenarios_draft.jsonl -> data/scenarios.jsonl
    python -m src.gen_context --only id1,id2  # pilot beliefs only
    python -m src.gen_context --dry-run       # mock model, dummy scenarios -> results/dryrun/

Each assistant turn is generated with the real history so far (system prompt + earlier pairs),
temperature 0. Every pair is printed for Trevor to read. Edit any bad turn by hand in the
output JSONL before freezing.
"""
import argparse
import sys
from pathlib import Path

from .client import make_client
from .common import CONTEXT_CONDS, ROOT, append_jsonl, load_config, load_scenarios, out_dir, parse_only


def fill(client, cfg, system_prompt, user_turns):
    model = cfg["reference_model"]["id"]
    msgs, out = [{"role": "system", "content": system_prompt}], []
    for u in user_turns:
        msgs.append({"role": "user", "content": u})
        r = client.chat(model, msgs, temperature=0, max_tokens=cfg.get("reference_max_tokens", 200))
        if r.get("finish_reason") == "length":
            sys.exit(f"Reference reply truncated (finish_reason=length): {r['text']!r}. Raise reference_max_tokens.")
        msgs.append({"role": "assistant", "content": r["text"]})
        out.append(r["text"])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp")
    ap.add_argument("--out")
    ap.add_argument("--only")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="overwrite an existing output file")
    ap.add_argument("--allow-draft", action="store_true", help="pilot only: accept unedited draft beliefs")
    a = ap.parse_args(argv)

    cfg = load_config()
    inp = a.inp or ROOT / "data" / ("scenarios_dummy.jsonl" if a.dry_run else "scenarios_draft.jsonl")
    out = Path(a.out) if a.out else (out_dir(True) / "scenarios.jsonl" if a.dry_run else ROOT / "data" / "scenarios.jsonl")
    if out.exists() and not a.force and not a.dry_run:
        sys.exit(f"{out} exists. It may be frozen. Use --force only if this is before the prereg freeze.")
    if out.exists():
        out.unlink()

    system_prompt = (ROOT / "prompts" / "neutral_assistant.md").read_text(encoding="utf-8").strip()
    client = make_client(cfg, a.dry_run)
    scen = load_scenarios(inp, require_assistant=False, only=parse_only(a.only))
    drafts = [s["id"] for s in scen if s.get("draft")]
    if drafts and not a.dry_run and not a.allow_draft:
        sys.exit(f'Still marked "draft": true (Trevor edits each, then removes the flag): {drafts}')

    for s in scen:
        for cond in CONTEXT_CONDS:
            s[cond]["assistant"] = fill(client, cfg, system_prompt, s[cond]["user"])
            print(f"\n===== {s['id']} · {cond} =====")
            for i, (u, asst) in enumerate(zip(s[cond]["user"], s[cond]["assistant"]), 1):
                print(f"[U{i}] {u}\n[A{i}] {asst}\n")
        append_jsonl(out, s)
        print(f"----- FINAL ({s['id']}): {s['final']}")

    print(f"\nWrote {len(scen)} scenarios -> {out}  |  spend ${client.tracker.spent:.4f}")
    print("READ every [A] turn. Fix any that agree, challenge, explain or advise, by hand, before freezing.")


if __name__ == "__main__":
    main()
