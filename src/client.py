"""The only module that talks to an API. OpenRouter via the openai SDK, retries, cost tracking, and a mock.

    client = make_client(cfg, dry_run=False)
    out = client.chat(model_id, messages, temperature=1.0, max_tokens=600)
    out -> {"text", "served_model", "usage": {"prompt_tokens", "completion_tokens", "cost"}}
"""
import hashlib
import json
import os
import random
import threading
import time

BASE_URL = "https://openrouter.ai/api/v1"
MAX_RETRIES = 5


class BudgetExceeded(RuntimeError):
    pass


class EmptyResponse(RuntimeError):
    """OpenRouter occasionally returns 200 with no choices or empty content. Treated as retryable."""


def model_prices(cfg):
    """{model_id: (usd_per_M_in, usd_per_M_out)} for every model in the config."""
    entries = list(cfg["models"]) + [cfg["reference_model"], cfg["grader_model"]]
    return {m["id"]: (float(m["price_in"]), float(m["price_out"])) for m in entries}


def approx_tokens(messages):
    return sum(len(m["content"]) for m in messages) // 4 + 4 * len(messages)


class CostTracker:
    """Running spend. Refuses a call whose worst case would cross the cap."""

    def __init__(self, prices, cap_usd):
        self.prices, self.cap, self.spent, self.calls = prices, float(cap_usd), 0.0, 0
        self._lock = threading.Lock()

    def price_of(self, model, prompt_tokens, completion_tokens):
        p_in, p_out = self.prices.get(model, (0.0, 0.0))
        return (prompt_tokens * p_in + completion_tokens * p_out) / 1e6

    def check(self, model, messages, max_tokens):
        worst = self.price_of(model, approx_tokens(messages), max_tokens)
        with self._lock:
            if self.spent + worst > self.cap:
                raise BudgetExceeded(f"spent ${self.spent:.4f}; next call could cost ${worst:.4f}; cap ${self.cap:.2f}")

    def add(self, model, usage):
        cost = usage.get("cost")
        if cost is None:
            cost = self.price_of(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        with self._lock:
            self.spent += cost
            self.calls += 1
        return cost


def _is_retryable(err):
    import openai
    if isinstance(err, (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError, EmptyResponse)):
        return True
    return isinstance(err, openai.APIStatusError) and err.status_code >= 500


class Client:
    def __init__(self, tracker, api_key=None):
        from openai import OpenAI
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY not set: copy .env.example to .env and fill it in")
        self._client = OpenAI(base_url=BASE_URL, api_key=key, timeout=120, max_retries=0)
        self.tracker = tracker

    def _call(self, model, messages, temperature, max_tokens):
        r = self._client.chat.completions.create(
            model=model, messages=messages, temperature=temperature, max_tokens=max_tokens,
            extra_body={"usage": {"include": True}},  # asks OpenRouter to report exact cost
        )
        if not r.choices or not r.choices[0].message or not r.choices[0].message.content:
            raise EmptyResponse(f"empty response from {model}")
        u = r.usage
        usage = {
            "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
            "cost": getattr(u, "cost", None),
        }
        return {"text": r.choices[0].message.content, "served_model": r.model,
                "finish_reason": r.choices[0].finish_reason, "usage": usage}

    def chat(self, model, messages, temperature, max_tokens):
        self.tracker.check(model, messages, max_tokens)
        for attempt in range(MAX_RETRIES + 1):
            try:
                out = self._call(model, messages, temperature, max_tokens)
                out["usage"]["cost"] = self.tracker.add(model, out["usage"])
                return out
            except Exception as e:  # noqa: BLE001: classify, then retry or re-raise
                if attempt == MAX_RETRIES or not _is_retryable(e):
                    raise
                time.sleep(2 ** (attempt + 1) + random.random())


class MockClient:
    """Deterministic fake for --dry-run and tests. Never touches the network.

    Grader prompts (they ask for JSON) get a JSON score derived from a hash of the reply,
    so the grading and analysis stages see a spread of scores.
    """

    def __init__(self, tracker):
        self.tracker = tracker

    def chat(self, model, messages, temperature, max_tokens):
        self.tracker.check(model, messages, max_tokens)
        last = messages[-1]["content"]
        h = int(hashlib.sha1((model + json.dumps(messages)).encode()).hexdigest(), 16)
        if "Respond with JSON only" in last:
            text = json.dumps({"score": h % 4, "reason": "mock grade"})
        else:
            text = f"[mock reply #{h % 1000} from {model} to: {last[:60]}]"
        usage = {"prompt_tokens": approx_tokens(messages), "completion_tokens": len(text) // 4, "cost": None}
        usage["cost"] = self.tracker.add(model, usage)
        return {"text": text, "served_model": f"{model}:mock", "finish_reason": "stop", "usage": usage}


def prior_spend(results_dir):
    """Spend already recorded in a results dir (replies + grades), so the cap holds across runs."""
    from .common import read_jsonl
    reply_cost = sum(r["usage"].get("cost") or 0 for r in read_jsonl(results_dir / "raw.jsonl"))
    grade_cost = sum(r["grade"].get("cost") or 0 for r in read_jsonl(results_dir / "graded.jsonl"))
    return reply_cost + grade_cost


def make_client(cfg, dry_run=False):
    tracker = CostTracker(model_prices(cfg), cfg.get("cost_cap_usd", 25.0))
    if dry_run:
        return MockClient(tracker)
    from dotenv import load_dotenv
    from .common import ROOT
    load_dotenv(ROOT / ".env")
    return Client(tracker)
