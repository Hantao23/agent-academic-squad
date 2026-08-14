# Model routing

Use these routes as defaults, not restrictions. The user's explicit choice always wins.

## Contents

- Selection sequence and model IDs
- Planning defaults
- Code and experiment defaults
- Mathematics defaults
- Paper defaults
- Review defaults
- Codex Radar
- Model availability

## Selection sequence

1. Identify the stage: planning, execution, or review.
2. Identify the domain: code/experiment, mathematics, or paper.
3. Judge workload cost and decision stakes independently.
4. Choose the default model and reasoning effort below.
5. Apply a user override.
6. For a high-workload, high-stakes, or uncertain choice, consult Codex Radar only when current model evidence could change the route.

Use these exact model IDs when dispatching:

- Sol: `gpt-5.6-sol`
- Terra: `gpt-5.6-terra`
- Luna: `gpt-5.6-luna`

The words `medium`, `high`, `xhigh`, `max`, and `ultra` refer to reasoning effort, not separate model IDs.

## Workload and decision stakes

Workload cost estimates the investigation, implementation, experiment, or reading effort required. Decision stakes estimate the harm of a wrong recommendation. Do not use either as a proxy for the other.

| Shape | Default handling |
| --- | --- |
| Bounded workload, ordinary stakes | Main may answer directly; use Sol medium or high if delegated |
| Bounded workload, high stakes | Narrow evidence review with Sol xhigh and an adaptive context handoff |
| High workload, ordinary stakes | Plan first when execution is not already authorized and accepted |
| High workload, high stakes | Plan first, expose material decisions, then use the appropriate strong executor or reviewer |

Example: “Should I rerun after changing the timing boundary, or derive a corrected metric from saved sub-timers?” is a code/experiment `review`, not execution or broad experiment planning. Its workload is bounded if the active context already identifies the timing code and result artifacts, while its decision stakes may be high. Use Sol xhigh to verify the timer nesting, field completeness, and reporting semantics; do not rerun experiments or reconstruct the repository context from scratch.

## Planning defaults

| Planning shape | Default |
| --- | --- |
| Short, explicit plan | Sol medium |
| Standard plan | Sol high |
| High-cost, cross-module, or open-ended plan | Sol xhigh |
| Mathematical proof or theoretical strategy | Sol max |

Return the plan and stop. A plan request does not authorize execution.

## Code and experiment defaults

| Work | Default |
| --- | --- |
| Mechanical or tightly scoped local code edit | Sol medium |
| Non-trivial work contained within one module | Sol high |
| Normal development, multi-file change, hard diagnosis, or code review | Sol xhigh |
| Critical algorithm or major architecture decision | Sol max |
| Standard experiment design | Sol high |
| Complex or costly experiment design | Sol xhigh |
| Execute a fixed, testable experiment protocol | Luna max |
| Debug code during experiment execution | Sol xhigh |
| Statistical or theoretical analysis | Sol max |

Use Sol ultra only when the user explicitly requests it or accepts a disclosed escalation.

## Mathematics defaults

| Work | Default |
| --- | --- |
| Check calculations or organize known formulas | Sol high |
| Analyze a strategy or construct an algorithm | Sol xhigh |
| Formal proof, difficult derivation, or statistical theory | Sol max |
| Extreme problem beyond the default route | Sol ultra with user approval |

## Paper defaults

Choose the primary workflow skill from [external-skills.md](external-skills.md).

| Work | Default |
| --- | --- |
| Broad literature search, deduplication, and first-pass screening | Luna max |
| Full-paper reading | Terra max |
| Extract and synthesize evidence across long sources | Terra max |
| Local rewrite or formatting adjustment | Sol medium |
| Standard paragraph writing or polishing | Sol high |
| Full section, core argument, or manuscript restructuring | Sol xhigh |
| Add or verify citations | Match search depth; normally Luna max |
| Scientific figure creation or revision | Sol high or xhigh |
| Data availability or FAIR metadata | Sol high |
| Pre-submission manuscript review | Sol xhigh |
| Reviewer response | Sol xhigh |

When a request combines reading and manuscript writing, let Terra max return grounded reading notes, then use Sol high or xhigh for the writing stage. Do not force two stages when one bounded task can produce the requested artifact reliably.

## Review defaults

- Use Sol high for a routine bounded review.
- Use Sol xhigh for normal code review, bounded but high-stakes experiment decisions, critical experiment conclusions, or submission-level paper review.
- Use Sol max for mathematical correctness.
- For bounded high-stakes review, verify the smallest set of decisive evidence. High stakes do not authorize broad investigation when the supplied evidence index is sufficient.
- Do not run review automatically. The user may review the result personally or ask for a reviewer.

## Codex Radar

Read the public feeds with `python3 scripts/radar_snapshot.py` when:

- the user asks for current model evidence;
- a high-workload or high-stakes task has two plausible routes;
- an escalation would materially change time or cost;
- a model appears degraded or a new model might change the default.

Skip the fetch when the user already selected an exact model, or when a bounded route is unambiguous.

Interpret the feeds conservatively:

- Use DeepSWE metrics for code and agentic software work only.
- Use Fast Radar for latency and generation speed only.
- Treat community ratings as a subjective secondary signal.
- Ignore benchmark points with fewer than 30 weighted samples and community scores with fewer than 20 ratings when making a default-route decision.
- Do not infer mathematics, literature-reading, or writing quality from a code benchmark.
- Prefer the pinned route when live evidence is missing, irrelevant, or statistically weak.
- If a live degradation signal changes a default route, disclose the changed assignment to the user.

Public feeds:

- `https://codex-reset-radar.pages.dev/api/radar-insights`
- `https://codex-reset-radar.pages.dev/api/intelligence-efficiency-metrics`
- `https://codex-reset-radar.pages.dev/api/model-ratings?view=public`
- `https://codex-reset-radar.pages.dev/data/fast-radar-history.json`

## Model availability

Use only models exposed by the current Codex environment. If an exact default is unavailable, report it instead of silently mapping to a different family. A user may authorize a temporary substitute.
