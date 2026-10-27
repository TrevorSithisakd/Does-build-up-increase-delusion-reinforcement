"""Shared helpers: config, paths, scenario loading/validation, message building, JSONL I/O."""
import hashlib
import json
import threading
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
THEMES = {"persecutory", "grandiose", "referential", "erotomanic", "ai-connection"}
N_TURNS = 6
CONTEXT_CONDS = ("buildup", "neutral")  # conditions that carry a prefilled conversation
ALL_CONDS = ("cold", "neutral", "buildup", "buildup3", "poscontrol")


def load_config(path=None):
    with open(path or ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def out_dir(dry_run=False, override=None):
    """results/ for real runs, results/dryrun/ for mock runs, or an explicit dir (e.g. results/pilot)."""
    d = Path(override) if override else ROOT / "results" / ("dryrun" if dry_run else "")
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------- scenarios ----------

def validate_scenario(s, require_assistant=True):
    """Raise ValueError describing the first problem found in one scenario dict."""
    sid = s.get("id", "<no id>")
    for field in ("id", "theme", "final"):
        if not isinstance(s.get(field), str) or not s[field].strip():
            raise ValueError(f"{sid}: missing or empty '{field}'")
    if s["theme"] not in THEMES:
        raise ValueError(f"{sid}: theme '{s['theme']}' not in {sorted(THEMES)}")
    for cond in CONTEXT_CONDS:
        block = s.get(cond)
        if not isinstance(block, dict):
            raise ValueError(f"{sid}: missing '{cond}' block")
        users = block.get("user")
        if not isinstance(users, list) or len(users) != N_TURNS or not all(isinstance(u, str) and u.strip() for u in users):
            raise ValueError(f"{sid}: '{cond}.user' must be {N_TURNS} non-empty strings")
        if require_assistant:
            asst = block.get("assistant")
            if not isinstance(asst, list) or len(asst) != N_TURNS or not all(isinstance(a, str) and a.strip() for a in asst):
                raise ValueError(f"{sid}: '{cond}.assistant' must be {N_TURNS} non-empty strings (run gen_context.py)")


def load_scenarios(path, require_assistant=True, only=None):
    scen = read_jsonl(path)
    ids = [s.get("id") for s in scen]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate scenario ids: {sorted(dupes)}")
    for s in scen:
        validate_scenario(s, require_assistant)
    if only:
        missing = set(only) - set(ids)
        if missing:
            raise ValueError(f"--only ids not found: {sorted(missing)}")
        scen = [s for s in scen if s["id"] in only]
    return scen


def parse_only(arg):
    return [x.strip() for x in arg.split(",") if x.strip()] if arg else None


# ---------- messages ----------

def build_messages(s, cond, poscontrol_system=None):
    """The exact message list a tested model sees. The final user message is identical across conditions."""
    msgs = []
    if cond == "poscontrol":
        if not poscontrol_system:
            raise ValueError("poscontrol needs poscontrol_system")
        msgs.append({"role": "system", "content": poscontrol_system})
    elif cond in ("buildup", "neutral", "buildup3"):
        block = s["buildup" if cond == "buildup3" else cond]
        n = 3 if cond == "buildup3" else N_TURNS
        for u, a in zip(block["user"][:n], block["assistant"][:n]):
            msgs += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    elif cond != "cold":
        raise ValueError(f"unknown condition '{cond}'")
    return msgs + [{"role": "user", "content": s["final"]}]


def record_key(sid, cond, model, sample):
    return hashlib.sha1(f"{sid}|{cond}|{model}|{sample}".encode()).hexdigest()


# ---------- JSONL ----------

_write_lock = threading.Lock()


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(path, obj):
    """Thread-safe append + flush, so a crash loses at most the call in flight."""
    with _write_lock, open(path, "a") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        f.flush()


def done_keys(path):
    return {r["key"] for r in read_jsonl(path)}
