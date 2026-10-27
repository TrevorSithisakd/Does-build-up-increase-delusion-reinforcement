"""Collect the final replies: every condition x tested model x sample.

    python -m src.run --dry-run                              # mock client, results/dryrun/
    python -m src.run --only id1,id2 --out results/pilot     # the pilot
    python -m src.run                                        # the full run (asks to confirm the estimate)

Resumes: a key (belief|condition|model|sample) already in raw.jsonl is skipped.
Failures go to errors.jsonl; re-running the same command retries exactly those.
The loop is sample-major, so an early stop leaves conditions balanced.
"""
import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from .client import BudgetExceeded, approx_tokens, make_client, prior_spend
from .common import (ROOT, append_jsonl, build_messages, done_keys, load_config, load_scenarios,
                     out_dir, parse_only, record_key)


def plan_jobs(scen, cfg, done):
    jobs = []
    for i in range(cfg["samples"]):
        for s in scen:
            for cond in cfg["conditions"]:
                msgs = build_messages(s, cond, cfg.get("poscontrol_system"))
                for m in cfg["models"]:
                    key = record_key(s["id"], cond, m["id"], i)
                    if key not in done:
                        jobs.append({"key": key, "s": s, "cond": cond, "model": m["id"], "sample": i, "msgs": msgs})
    return jobs


def estimate(jobs, client, cfg):
    """Rough upper bound: approx prompt tokens + max_tokens completion, at config prices."""
    return sum(client.tracker.price_of(j["model"], approx_tokens(j["msgs"]), cfg["max_tokens"]) for j in jobs)


def do_job(client, cfg, j):
    r = client.chat(j["model"], j["msgs"], temperature=cfg["temperature"], max_tokens=cfg["max_tokens"])
    s = j["s"]
    return {"key": j["key"], "id": s["id"], "theme": s["theme"], "cond": j["cond"], "model": j["model"],
            "served_model": r["served_model"], "sample": j["sample"], "n_messages": len(j["msgs"]),
            "final": s["final"], "reply": r["text"], "finish_reason": r["finish_reason"], "usage": r["usage"],
            "ts": datetime.now(timezone.utc).isoformat()}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios")
    ap.add_argument("--out", help="output dir (default results/, or results/dryrun/ with --dry-run)")
    ap.add_argument("--only")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    ap.add_argument("--workers", type=int)
    a = ap.parse_args(argv)

    cfg = load_config()
    d = out_dir(a.dry_run, a.out)
    if a.scenarios:
        spath = a.scenarios
    elif a.dry_run:
        gen = out_dir(True) / "scenarios.jsonl"
        spath = gen if gen.exists() else ROOT / "data" / "scenarios_dummy.jsonl"
    else:
        spath = ROOT / "data" / "scenarios.jsonl"
    scen = load_scenarios(spath, require_assistant=True, only=parse_only(a.only))

    client = make_client(cfg, a.dry_run)
    client.tracker.spent = prior_spend(d)  # the cap is cumulative across runs into this dir
    raw, err = d / "raw.jsonl", d / "errors.jsonl"
    jobs = plan_jobs(scen, cfg, done_keys(raw))
    est = estimate(jobs, client, cfg)
    print(f"{len(scen)} beliefs x {len(cfg['conditions'])} conditions x {len(cfg['models'])} models x "
          f"{cfg['samples']} samples | {len(jobs)} calls to do | est. <= ${est:.2f} | spent so far ${client.tracker.spent:.2f} (cap ${client.tracker.cap:.2f})")
    print(f"scenarios: {spath}\noutput:    {raw}")
    if not jobs:
        print("Nothing to do.")
        return 0
    if not (a.dry_run or a.yes) and input("Proceed? [y/N] ").strip().lower() != "y":
        return 1

    n_ok = n_err = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=a.workers or cfg.get("workers", 8)) as pool:
        futs = {pool.submit(do_job, client, cfg, j): j for j in jobs}
        try:
            for f in as_completed(futs):
                j = futs[f]
                try:
                    append_jsonl(raw, f.result())
                    n_ok += 1
                except BudgetExceeded:
                    raise
                except Exception as e:  # noqa: BLE001: logged and retried on the next run
                    n_err += 1
                    append_jsonl(err, {"key": j["key"], "id": j["s"]["id"], "cond": j["cond"], "model": j["model"],
                                       "sample": j["sample"], "error": f"{type(e).__name__}: {e}"[:500],
                                       "ts": datetime.now(timezone.utc).isoformat()})
                if (n_ok + n_err) % 25 == 0:
                    print(f"  {n_ok + n_err}/{len(jobs)} | ok {n_ok} err {n_err} | ${client.tracker.spent:.4f}")
        except BudgetExceeded as e:
            for f in futs:
                f.cancel()
            print(f"STOPPED at cost cap: {e}")
            return 2

    print(f"Done in {time.time() - t0:.0f}s | ok {n_ok} | errors {n_err} | spend ${client.tracker.spent:.4f}")
    if n_err:
        print(f"Errors logged to {err}. Re-run the same command to retry them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
