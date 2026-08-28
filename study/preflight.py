"""E00 pre-flight (§04): three questions for five cents.

1. Does implicit caching survive the LiteLLM proxy? (cached_tokens > 0 on repeats)
2. Are thinking tokens reported, and how large?
3. Is per-call cost reported (header/field), or do we price from tokens?

Run:  LITELLM_KEY=... .venv/bin/python -m study.preflight
"""
from __future__ import annotations

import json
import os
import sys
import time

from openai import OpenAI

from study.config import KEY_ENV, PRIMARY_MODEL, PROXY_BASE_URL


def main() -> int:
    key = os.environ.get(KEY_ENV)
    if not key:
        print(f"set {KEY_ENV} first"); return 2
    client = OpenAI(api_key=key, base_url=PROXY_BASE_URL)

    big = "".join("def helper_%d():\n    return %d\n" % (i, i) for i in range(800))
    results = []
    for i in range(3):
        r = client.chat.completions.with_raw_response.create(
            model=PRIMARY_MODEL,
            messages=[{"role": "user", "content": big + f"\n# call {i}\nReply with exactly: ok"}],
            max_tokens=16,
        )
        parsed = r.parse()
        u = parsed.usage.model_dump()
        cost_hdr = {k: v for k, v in r.headers.items() if "cost" in k.lower() or "spend" in k.lower()}
        results.append({"call": i, "usage": u, "cost_headers": cost_hdr})
        print(f"--- call {i} ---")
        print(json.dumps(u, indent=2))
        if cost_hdr:
            print("cost headers:", cost_hdr)
        time.sleep(1)

    def cached(u):
        return ((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0

    c1, c2 = cached(results[1]["usage"]), cached(results[2]["usage"])
    think = (results[0]["usage"].get("completion_tokens_details") or {}).get("reasoning_tokens")
    print("\n================ VERDICT ================")
    print(f"CHECK 1 caching:  call1={c1} call2={c2} cached tokens -> "
          + ("PASS (cost axis is MEASURED)" if (c1 or c2) else "FAIL (cost axis is MODELLED; ~5x bill — re-plan!)"))
    print(f"CHECK 2 thinking: reasoning_tokens={think!r}"
          + ("" if not think else "  -> fix a low reasoning effort, hold constant across arms"))
    any_hdr = any(r["cost_headers"] for r in results)
    print(f"CHECK 3 cost:     headers {'present' if any_hdr else 'absent -> price from tokens (frozen table)'}")
    with open(os.path.join(os.path.dirname(__file__), "preflight.result.json"), "w") as f:
        json.dump(results, f, indent=2)
    return 0 if (c1 or c2) else 1


if __name__ == "__main__":
    sys.exit(main())
