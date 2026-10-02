#!/usr/bin/env python3
"""StarGen: generate → verify → conserve (independent reasoning loop, v1).

For each battery item (verifiable by formula), a small LOCAL model proposes K
candidate traces at temperature; the formula (not vibes) decides; correct
traces archive to LTM; NEW skeletons (unseen procedure_sig) count as novelty.
Novelty rate = correct traces whose skeleton the system never saw.

Battery v1: handshake (n(n-1)/2), work_inverse (n1*t1/t2). Both closed-form,
zero ambiguity, infinite fresh numbers via curiosity-style swaps.

  python scripts/stargen.py --per 4 --model Qwen/Qwen2.5-1.5B-Instruct
"""
import argparse
import json
import random
import re
import sys
import time
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from service.memory.store import ProcedureStore, _procedure_sig

BATTERY = [
    ("In a group of {n} people each shakes hands with every other exactly once how many handshakes?",
     lambda n: n * (n - 1) // 2, "handshake"),
    ("{n1} builders can build a house in {t1} days. How many builders are needed to finish in {t2} days?",
     lambda n1, t1, t2: n1 * t1 // t2 if (n1 * t1) % t2 == 0 else None, "work_inverse"),
]

PROMPT = """Be concise (max 6 short steps). Solve step by step, ending with exactly: ANSWER: <integer>
Question: {q}
Trace:"""


def gen_trace(model, tok, q: str, temp: float = 0.8) -> str:
    import torch
    text = tok.apply_chat_template([{"role": "user", "content": PROMPT.format(q=q)}],
                                   tokenize=False, add_generation_prompt=True)
    ids = tok([text], return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=320, do_sample=True,
                             temperature=temp, pad_token_id=tok.eos_token_id)
    trace = tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
    # Pass 2 (format forcing): short greedy extraction — reasoning stays free,
    # the answer tag is constrained. Fixes the #1 failure mode (no ANSWER tag).
    probe = (text + trace + "\nNow reply with ONLY the final line in exactly "
             "this format: ANSWER: <integer>\nANSWER:")
    pids = tok([probe], return_tensors="pt").to(model.device)
    with torch.no_grad():
        out2 = model.generate(**pids, max_new_tokens=12, do_sample=False,
                              pad_token_id=tok.eos_token_id)
    tag = tok.decode(out2[0][pids["input_ids"].shape[1]:], skip_special_tokens=True)
    m = re.findall(r"(-?\d+)", tag)
    if m:
        trace = trace.rstrip() + f"\nANSWER: {m[-1]}"
    return trace


def extract_answer(trace: str):
    m = re.findall(r"ANSWER:\s*(-?\d+)", trace)
    if m:
        return int(m[-1])
    m = re.findall(r"[Aa]nswer is (-?\d+)", trace)
    if m:
        return int(m[-1])
    m = re.findall(r"=\s*(-?\d+)[.\s]*$", trace.strip())
    if m:
        return int(m[-1])
    nums = re.findall(r"-?\d+", trace)
    return int(nums[-1]) if nums else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per", type=int, default=4)
    ap.add_argument("--cases", type=int, default=3,
                    help="cases per family (bigger battery, less noise)")
    ap.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--mem", default="data/stargen_memory.json")
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"loading {args.model} on {device} ...", flush=True)
    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype="auto").to(device).eval()

    store = ProcedureStore(path=_REPO / args.mem)
    rng = random.Random(args.seed)
    known = {e.get("procedure_sig") for e in store.entries.values()}
    correct = novel = total = 0
    t0 = time.time()
    for tmpl, fn, fam in BATTERY:
        if fam == "handshake":
            cases = [{"n": rng.randint(20, 200)} for _ in range(args.cases)]
        else:
            cases = []
            while len(cases) < args.cases:
                n1, t1, t2 = rng.randint(4, 30), rng.randint(5, 30), rng.randint(2, 10)
                if (n1 * t1) % t2 == 0:
                    cases.append({"n1": n1, "t1": t1, "t2": t2})
        for kw in cases:
            exp = fn(**kw)
            if exp is None:
                continue
            q = tmpl.format(**kw)
            for _ in range(args.per):
                total += 1
                tr = gen_trace(model, tok, q)
                got = extract_answer(tr)
                if got == exp:
                    correct += 1
                    sig = _procedure_sig(tr)
                    if sig not in known:
                        novel += 1
                        known.add(sig)
                    store.remember_trace(q, tr[:600], str(exp), tier=f"stargen-{fam}",
                                        confidence=0.9)
    dt = time.time() - t0
    print(f"\ncorrect={correct}/{total} novel_skeletons={novel} "
          f"novelty_rate={novel / max(total, 1):.3f} entries={store.size()} ({dt:.0f}s)")
    print("READ: correct = verifier quality gate; novel = new reasoning skeletons the system never saw.")


if __name__ == "__main__":
    main()
