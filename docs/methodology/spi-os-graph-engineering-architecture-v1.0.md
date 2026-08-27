# SPI-OS Graph Engineering Architecture v1.0

**Status:** ADOPT — SPI-OS core architecture principle  
**Recorded:** 2026-08-28  
**Conceptual source:** LunarResearcher, “Graph Engineering: The Complete Guide to Building Multi-Agent AI Systems,” 2026-08-08.

This is an architecture principle, not a new standalone tool or agent package.

## Purpose

SPI multi-agent work should be orchestrated as a dependency graph rather than as a long chain of chats. The graph defines what can run in parallel, what structured state crosses each edge, where deterministic reduction occurs, how findings are challenged, how failures degrade, and which irreversible transitions require human approval.

## Core principles

1. **Dependency before sequence.** An edge exists only when downstream work consumes explicit upstream data.
2. **Structured state.** Nodes exchange defined objects rather than entire chat transcripts.
3. **Deterministic reducers.** Deduplication, sorting, normalization, schema validation, counting, and filtering should be code-first.
4. **Asymmetric verification.** Workers seek the strongest supported answer; verifiers try to falsify or reject it.
5. **Failure domains.** Nodes have retry, fallback, structured-failure, quorum-continuation, and critical-block policies.
6. **Width budgets.** Parallelism is bounded by unique coverage, reconciliation cost, spend, rate limits, and latency.
7. **Critical-path optimization.** Optimize unavoidable dependency latency, not merely node count.
8. **Human approval edges.** Irreversible actions remain unreachable until explicit approval state exists.
9. **Frozen constraints.** Evidence, execution-state, credential, publication, safety, and financial controls live outside agent optimization.
10. **Graph observability.** Track critical-path latency, node failure rate, retry rate, verifier kill rate, fan-out efficiency, compression ratio, and human intervention rate.

## Frozen constraints examples

- Never represent an engine as executed when it was not executed.
- Never mark a test as passed unless it actually ran.
- Never cite evidence as verified unless the source was inspected.
- Never expose or modify production credentials through public assets.
- Never perform irreversible external publication, deletion, permission change, or financial execution unless the required approval edge is satisfied.

## Reference topologies

- Fork / Join
- Escalation Ladder
- Tournament
- Map → Reduce → Verify → Synthesize
- Bounded Discovery Loop

## Target SPI research graph

Sources / data collectors  
→ parallel extraction and domain analysis  
→ deterministic normalize + dedupe + schema validation  
→ SEFM / SICAM or relevant analytical engines  
→ adversarial verifier  
→ synthesis  
→ Director approval edge where publication/action is irreversible  
→ publication/output layer.

## Target SPI investment graph

Market/data sources  
→ parallel HIPM / HISM / BCVM / HFGM / HAPM and permitted auxiliary models  
→ deterministic reducer  
→ adversarial verification and risk checks  
→ portfolio / trade synthesis  
→ Director approval edge for any real-money execution  
→ execution layer.

## State / handoff rule

Continuity should not rely primarily on compressed chat transcripts. Persist graph state: project, current state, completed nodes, pending nodes, blockers, last verified result, model/data versions, storage locations, and next action. Later sessions resume from state rather than reconstructing history from conversation memory.

## Implementation gate

Before adding an agent or edge, answer: **What exact data crosses this edge?** If the answer is only that the previous task finished, the dependency is presumptively fake and should be removed.

## Next action

Map existing SPI agents, models, memory systems, verification layers, and output engines into **SPI Agent Graph v1.0**. Do not create additional agents merely to satisfy the graph architecture.
