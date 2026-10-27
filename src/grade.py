"""Grade every reply with the reality-distortion schema, BLIND to condition.

    python -m src.grade --dry-run
    python -m src.grade --out results/pilot
    python -m src.grade

The grader prompt is built from exactly two strings, the final user message and the reply.
Condition, model and earlier turns never enter it (see tests/test_grade.py).
Unparseable output is retried once, then stored as score=None with the raw text.
Resumes by key, like run.py.
"""
import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from .client import BudgetExceeded, approx_tokens, make_client, prior_spend
from .common import ROOT, append_jsonl, done_keys, load_config, out_dir, read_jsonl

SCHEMA_MARKER = "<!-- BEGIN SCHEMA -->\n"


def load_schema():
    text = (ROOT / "prompts" / "rubric_reality_distortion.md").read_text()
    return text.split(SCHEMA_MARKER, 1)[1].strip()


def load_template():
    return (ROOT / "prompts" / "grader.md").read_text()


def build_grader_prompt(template, schema, final, reply):
    # SCHEMA first so a reply containing "<<FINAL>>" can't be re-substituted
    return template.replace("<<SCHEMA>>", schema).replace("<<FINAL>>", final).replace("<<REPLY>>", reply)


def parse_grade(text):
    """Return {"score": int 0-3, "reason": str} or None if the text has no valid grade."""
    if not text:
        return None
    t = re.sub(r"```(?:json)?", "", text)
    for m in re.finditer(r"\{[^{}]*\}", t, re.S):
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        score = obj.get("score")
        if isinstance(score, str) and score.strip().isdigit():
            score = int(score.strip())
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 3:
            continue
        return {"score": score, "reason": str(obj.get("reason", ""))}
    return None


def grade_one(client, cfg, prompt):
    model = cfg["grader_model"]["id"]
    msgs = [{"role": "user", "content": prompt}]
    texts, cost = [], 0.0
    for _ in range(2):  # one retry on unparseable output
        r = client.chat(model, msgs, temperature=0, max_tokens=cfg.get("grader_max_tokens", 300))
        texts.append(r["text"])
        cost += r["usage"]["cost"]
        g = parse_grade(r["text"])
        if g:
            return {**g, "grader_model": r["served_model"], "attempts": len(texts), "cost": cost}
    return {"score": None, "reason": "UNPARSEABLE: " + " ||| ".join(texts)[:1000],
            "grader_model": r["served_model"], "attempts": len(texts), "cost": cost}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="results dir holding raw.jsonl (default results/ or results/dryrun/)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--workers", type=int)
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    a = ap.parse_args(argv)

    cfg = load_config()
    d = out_dir(a.dry_run, a.out)
    rows = read_jsonl(d / "raw.jsonl")
    graded_path = d / "graded.jsonl"
    done = done_keys(graded_path)
    todo = [r for r in rows if r["key"] not in done]
    print(f"{len(rows)} replies | {len(todo)} to grade | grader {cfg['grader_model']['id']}")
    if not todo:
        return 0

    template, schema = load_template(), load_schema()
    client = make_client(cfg, a.dry_run)
    client.tracker.spent = prior_spend(d)
    gm = cfg["grader_model"]["id"]
    est = sum(client.tracker.price_of(gm, approx_tokens([{"role": "user", "content": build_grader_prompt(
        template, schema, r["final"], r["reply"])}]), cfg.get("grader_max_tokens", 300)) for r in todo)
    print(f"est. <= ${est:.2f} | already spent in {d.name or 'results'}/ ${client.tracker.spent:.2f} | cap ${client.tracker.cap:.2f}")
    if not (a.dry_run or a.yes) and input("Proceed? [y/N] ").strip().lower() != "y":
        return 1
    n_null = 0
    with ThreadPoolExecutor(max_workers=a.workers or cfg.get("workers", 8)) as pool:
        futs = {pool.submit(grade_one, client, cfg, build_grader_prompt(template, schema, r["final"], r["reply"])): r
                for r in todo}
        try:
            for i, f in enumerate(as_completed(futs), 1):
                r = futs[f]
                try:
                    g = f.result()
                except BudgetExceeded:
                    raise
                except Exception as e:  # noqa: BLE001: not written, so the next run retries it
                    print(f"  grade failed for {r['key'][:8]}: {type(e).__name__}: {e}")
                    continue
                n_null += g["score"] is None
                append_jsonl(graded_path, {**r, "grade": g})
                if i % 50 == 0:
                    print(f"  {i}/{len(todo)} | ${client.tracker.spent:.4f}")
        except BudgetExceeded as e:
            for f in futs:
                f.cancel()
            print(f"STOPPED at cost cap: {e}")
            return 2

    print(f"Graded -> {graded_path} | unparseable {n_null} | spend ${client.tracker.spent:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
