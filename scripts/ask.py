#!/usr/bin/env python3
"""Ask: conversational intermediary over the service (v1, read-only tools).

A small LOCAL model (Qwen2.5-1.5B-Instruct via transformers, $0, private)
translates natural language into service actions and reports back. Strict
ReAct loop with a tool budget: the model reasons about ROUTING, the service
does the knowing (memory, retrieval, judges). v1 tools are read-only —
nothing is written, seeded, or trained from here.

  python scripts/ask.py --q "cuantos Nobel tiene Israel?"
  python scripts/ask.py --repl   # chat loop (Ctrl-D to exit)

Backend: local transformers on CUDA if present, else CPU (slow).
"""
import argparse
import json
import re
import sys
from pathlib import Path as _P

_REPO = _P(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

SYSTEM = """You are the intermediary for a truth-hierarchy service. Answer the user by
calling TOOLS (never invent facts). Format tool calls exactly as:

```tool:resolve({{"question": "What type is pikachu?", "connectors": ["pokeapi"]}})
```

Available tools (JSON args like the example above, one call per block):
- resolve: answer a factual question. Args: question (required), connectors (optional list from: pokeapi, wikidata, openalex, local_docs, search).
- results: show a results board. Args: name in [longitudinal, market, formations, rounds].
- memory: show memory stats. Args: empty object.
- connectors: list sources. Args: empty object.
- shell: run a JAILED shell command (read-only probes free; writes need approve true).
  Args: command (required), approve (true only if the user explicitly allowed writes).

Rules: factual questions → resolve (pick the likely connector; pokeapi only for Pokemon). "How are we doing / resultados" → results board(s). If a call fails or returns null, say so honestly and suggest what would fix it (e.g. ingest a corpus). Max {budget} tool calls, then answer with what you have, citing sources[].

CRITICAL: your FIRST output must be exactly one tool call and nothing else.
Examples:
user: What type is pikachu?
```tool:resolve({{"question": "What type is pikachu?", "connectors": ["pokeapi"]}})
```
user: show me the rounds board
```tool:results({{"name": "rounds"}})
```"""

TOOL_RE = re.compile(r"(?:```)?tool:(\w+)\((\{.*?\})\)", re.S)


def build_tools():
    from service.connectors.registry import build_retrievers, describe_registry
    from service.corroboration import Corroborator
    from service.memory.store import ProcedureStore
    from service.results import board
    from service.router import Router

    mem = ProcedureStore(path=_REPO / "data" / "ask_memory.json")
    router = Router(memory=mem, corroborator=Corroborator(),
                    retrievers=build_retrievers(enabled_only=True), backends=[])

    def resolve(a):
        if not a.get("connectors"):
            rr = router.resolve(a["question"])
        else:
            rs = build_retrievers(enabled_only=False, include=a["connectors"])
            scoped = Router(memory=mem, corroborator=Corroborator(),
                            retrievers=rs, backends=[])
            rr = scoped.resolve(a["question"])
        return {"answer": rr.answer, "tier": rr.tier, "status": rr.status,
                "sources": rr.sources, "disagreement": rr.disagreement}

    return {
        "resolve": resolve,
        "results": lambda a: board(a.get("name", "longitudinal")),
        "memory": lambda a: {"entries": mem.size()},
        "connectors": lambda a: [c["name"] for c in describe_registry()],
        "shell": lambda a: __import__("service.sandbox", fromlist=["run"]).run(
            a.get("command", ""), approve=bool(a.get("approve", False))),
    }


def run_turn(model, tok, tools, question: str, budget: int = 6, verbose: bool = False):
    messages = [{"role": "system", "content": SYSTEM.format(budget=budget)},
                {"role": "user", "content": question}]
    calls = 0
    while calls < budget:
        text = generate(model, tok, messages)
        m = TOOL_RE.search(text)
        if not m:
            # Safety net: factual-looking question with zero calls → one forced resolve.
            if calls == 0 and question.strip().endswith("?"):
                try:
                    out = tools["resolve"]({"question": question})
                    calls += 1
                    if verbose:
                        print(f"[forced resolve -> {json.dumps(out)[:200]}]")
                    messages.append({"role": "assistant", "content": text})
                    messages.append({"role": "user",
                                     "content": f"Tool `resolve` returned:\n{json.dumps(out)[:2000]}\n"
                                                f"Continue (tools left: {budget - calls}) or answer."})
                    continue
                except Exception:
                    pass
            return text.strip(), calls
        name, raw = m.group(1), m.group(2)
        try:
            args = json.loads(raw)
            out = tools[name](args) if name in tools else {"error": f"unknown tool {name}"}
        except Exception as e:
            out = {"error": f"{type(e).__name__}: {e}"}
        calls += 1
        if verbose:
            print(f"[tool:{name} -> {json.dumps(out)[:200]}]")
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user",
                         "content": f"Tool `{name}` returned:\n{json.dumps(out)[:2000]}\n"
                                    f"Continue (tools left: {budget - calls}) or answer."})
    # budget spent: force final answer
    messages.append({"role": "user", "content": "No more tool calls. Answer now with what you have."})
    return generate(model, tok, messages).strip(), calls


def generate(model, tok, messages: list) -> str:
    import torch
    text = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    ids = tok([text], return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(**ids, max_new_tokens=256, do_sample=False,
                             pad_token_id=tok.eos_token_id)
    gen = out[0][ids["input_ids"].shape[1]:]
    return tok.decode(gen, skip_special_tokens=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--q")
    ap.add_argument("--repl", action="store_true")
    ap.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    ap.add_argument("--budget", type=int, default=6)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"loading {args.model} on {device} ...", flush=True)
    tok = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(args.model, dtype="auto").to(device).eval()
    tools = build_tools()

    def ask(q):
        ans, n = run_turn(model, tok, tools, q, budget=args.budget, verbose=args.verbose)
        print(f"\n{ans}\n[calls: {n}]")

    if args.repl:
        print("ask> (Ctrl-D para salir)")
        try:
            while True:
                q = input("\nask> ").strip()
                if q:
                    ask(q)
        except EOFError:
            pass
    elif args.q:
        ask(args.q)
    else:
        ap.error("give --q or --repl")


if __name__ == "__main__":
    main()
