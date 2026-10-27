"""Draw 40 graded replies for Trevor to hand-score, with condition, model and grader score hidden.

    python -m src.sample_for_labels            # -> results/human_labels.csv + results/labels_key.csv
    python -m src.sample_for_labels --dry-run

Stratified: replies are shuffled within each condition x model cell, then drawn round-robin
across cells, so every cell is represented as evenly as 40 allows. The final order is shuffled again.
human_labels.csv shows only label_id, final, reply and an empty human_score column.
labels_key.csv maps label_id -> raw key (a hash), which reveals nothing by itself.
Refuses to overwrite an existing labels file.
"""
import argparse
import csv
import random
import sys
from collections import defaultdict

from .common import load_config, out_dir, read_jsonl

N_LABELS = 40


def stratified_sample(rows, n, seed):
    rng = random.Random(seed)
    cells = defaultdict(list)
    for r in rows:
        cells[(r["cond"], r["model"])].append(r)
    order = sorted(cells)
    for c in order:
        rng.shuffle(cells[c])
    picked = []
    while len(picked) < n and any(cells[c] for c in order):
        for c in order:
            if cells[c] and len(picked) < n:
                picked.append(cells[c].pop())
    rng.shuffle(picked)
    return picked


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--n", type=int, default=N_LABELS)
    a = ap.parse_args(argv)

    cfg = load_config()
    d = out_dir(a.dry_run, a.out)
    labels, key = d / "human_labels.csv", d / "labels_key.csv"
    if labels.exists():
        sys.exit(f"{labels} already exists. Not overwriting hand labels.")
    rows = [r for r in read_jsonl(d / "graded.jsonl") if r["grade"]["score"] is not None]
    picked = stratified_sample(rows, a.n, cfg.get("seed", 2026))

    with open(labels, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label_id", "final", "reply", "human_score"])
        for i, r in enumerate(picked, 1):
            w.writerow([f"L{i:02d}", r["final"], r["reply"], ""])
    with open(key, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label_id", "key"])
        for i, r in enumerate(picked, 1):
            w.writerow([f"L{i:02d}", r["key"]])

    print(f"Wrote {len(picked)} replies -> {labels}")
    print("Score each 0-3 with prompts/rubric_reality_distortion.md. Do NOT open graded.jsonl or labels_key.csv first.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
