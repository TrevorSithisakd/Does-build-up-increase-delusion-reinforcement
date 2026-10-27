"""Read replies as text.

    python -m src.show --out results/pilot      # pilot: every reply, grouped by belief (T9)
    python -m src.show --spot 10                # full run: 10 random replies, condition + grade HIDDEN (T13)

Grouping by belief puts the four conditions for the same final message side by side.
On the main results/ dir only --spot is allowed, so nothing here can leak rates before the labels gate.
"""
import argparse
import random
import sys

from .common import ROOT, load_config, out_dir, read_jsonl


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--spot", type=int, help="N random replies, blind")
    a = ap.parse_args(argv)

    d = out_dir(a.dry_run, a.out)
    graded = {r["key"]: r["grade"] for r in read_jsonl(d / "graded.jsonl")}
    rows = read_jsonl(d / "raw.jsonl")

    if a.spot:
        for r in random.Random().sample(rows, min(a.spot, len(rows))):
            print(f"----- {r['key'][:8]} · served {r['served_model']} · finish {r['finish_reason']}\n{r['reply']}\n")
        return 0
    if d.resolve() == (ROOT / "results").resolve():
        sys.exit("On the main results/ dir use --spot N (blind). Full grouped view is for the pilot only.")

    order = {c: i for i, c in enumerate(load_config()["conditions"])}
    rows.sort(key=lambda r: (r["id"], order.get(r["cond"], 99), r["model"], r["sample"]))
    current = None
    for r in rows:
        if r["id"] != current:
            current = r["id"]
            print(f"\n{'=' * 80}\n{r['id']} ({r['theme']})\nFINAL: {r['final']}\n{'=' * 80}")
        g = graded.get(r["key"])
        tag = f"score {g['score']} · {g['reason']}" if g else "ungraded"
        print(f"\n--- {r['cond']} · {r['model']} · s{r['sample']} · {tag}\n{r['reply']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
