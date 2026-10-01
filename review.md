Strengths I see:
Process memory, not data memory — This is the core bet, and it's defensible. You're storing procedure_sig (question patterns), learning curves (attempts/successes), and outcomes — not raw facts. That's lean and replicable across instances.

Tier-based escalation — Reflexes (fast LTM) → Judgments (routes) → Deliberation (models) is a real discipline. Most systems throw everything at the LLM; you're forcing deterministic paths first. That's operationally sound.

Monotonicity guarantee — Versioned LTM never regresses. In a production system that learns live, this is critical and rarely enforced. Good.

Standalone repo — No ../cognitive-swarm crosspaths, no coupled Dockerfiles. That's harder to maintain initially but right long-term for a service layer.

Curiosity budget + novelty filtering — The idea that the system learns what it doesn't know (via attempts/successes imbalance) and mutates queries deliberately is clever. Most systems are passive.

Concerns / Tensions:
"Small models + deterministic patterns beat big models" — This is your thesis, and it's falsifiable by design (good). But the falsification mechanism is escalation-rate decay over time. That's real, but:

How do you separate "the system learned better heuristics" from "the traffic distribution shifted"?
What's your baseline escalation rate? 10%? 50%? Without this, "it's working" is hard to measure.
Jev (the judgment layer) — You've designed 5 decision seats. But:

These are heuristics, not learned. If the thesis is that learning beats big models, why aren't these thresholds adaptive?
Or is the design intentionally conservative (heuristics never break; only LTM enriches)?
Corroboration without recency — You explicitly call this out: reliability + independence exist, recency doesn't yet. That's a gap. Sources can be reliable and stale. How long before recency lands?

Federated learning — You call this "next-level bet" and it's unbuilt. Without it, each instance starts cold on procedures. The network-effect moat only exists later. Until then, you're running 10 separate cold systems.

Weekly distillation pipeline — Also unbuilt. You've designed LoRA compression + holdout gate, but:

How do you guard against distilled models "hallucinating" generalizations?
The shadow week + promote/rollback is smart, but it's a 2-week loop. How do you handle urgent fixes?
Questions I'd ask:
Procedure cold start: A new customer starts with empty LTM. Do you warm it from a corpus (already designed: scripts/ingest_corpus.py)? Or do you accept high escalation-to-models for week 1?
Outcome labeling: record_outcome() is the engine. Who labels? Is it user feedback, backend verification, or heuristic?
Model selection per-request: You support phi/qwen MLX + minimax-m3. What's the routing logic? Or is it operator-chosen?
Bottom line:
This is architecturally sound — it's a bet on process over scale, with guardrails. The biggest risk isn't the design; it's execution velocity on the unbuilt pieces (curiosity, distillation, federation). If those stay designs and you ship the core + corroboration, you'll have a solid operational layer that beats naive LLM APIs on cost and latency.

The monotonicity guarantee and tier discipline are your moats. Keep those.

