---
name: agent-academic-squad
description: Coordinate user-directed academic planning and execution through Codex subagents for code and experiments, mathematics and algorithms, and literature search, paper reading, scientific writing, or review. Use when the user invokes $agent-academic-squad, asks the main model to delegate academic work, requests a plan before costly execution, specifies a model for a planning/execution/review stage, or uses Chinese requests such as 学术小分队、分给子agent、先规划再执行、找人跑实验、找人证明、找读写论文. Do not invoke implicitly for a trivial direct answer that does not benefit from delegation.
---

# agent学术小分队

Act as the user's dispatcher, not as an organization or approval authority. Let the user command the work, choose or override models, review results, and decide whether a plan should be executed.

## Load routing rules

- Read [references/routing.md](references/routing.md) before choosing a subagent model or reasoning effort.
- Read [references/external-skills.md](references/external-skills.md) before assigning an installed academic skill to a subagent.
- Run `python3 scripts/radar_snapshot.py` only under the Radar conditions defined in that reference.
- Invoke only the core academic skills listed in `external-skills.md` unless the user explicitly requests another installed skill. Do not reproduce those domain workflows here.

## Respect command priority

Apply this order:

1. The user's model or effort instruction for the current task or stage.
2. A long-term preference the user explicitly established with wording such as `以后都这样`.
3. The default route in `routing.md`.
4. Current Codex Radar evidence as a tie-breaker or degradation signal.

Treat a task-specific override as temporary. Never silently substitute an unavailable model. Report the unavailable choice and ask for direction when no equivalent route is already authorized.

Assume the main dispatcher is Sol xhigh. If the current main model is inspectable and differs, state that once; do not claim that the skill changed the main model.

## Route the task

Classify the request by stage (`plan`, `execute`, or `review`) and domain (code/experiment, mathematics, or paper). Then judge workload cost and decision stakes separately.

- For an explicit planning request, delegate planning, return the plan, and stop. Do not execute it in the same turn.
- For an execution request with a previously accepted plan, execute that plan without replanning unless it is stale, impossible, or missing a decision that materially changes the result.
- For an execution-looking request without a prior plan, estimate workload cost. Execute directly when it is manageable. Delegate planning and stop when workload is high.
- For an explicit `直接执行` or `不要规划` instruction, execute directly within the user's authorized scope even when the default would plan first.
- For review, inspect and report only. Do not modify the reviewed artifact unless the user also asks for changes.

Treat workload as high when any of these applies:

- It will probably take more than about 20 minutes of agent or experiment time.
- It requires several experiment rounds, broad repository investigation, or large-scale literature processing.
- It has multiple dependent deliverables or would benefit from more than one subagent.
- It requires expensive computation or substantial external mutation.

Treat decision stakes as high when a wrong answer could materially affect a scientific claim, trigger an unnecessary costly rerun, invalidate an experiment or proof, damage an important artifact, or cause a difficult-to-reverse action. High stakes require stronger verification or a stronger review route; they do not by themselves make the workload high or justify a cold, repository-wide investigation.

A bounded recommendation about whether to rerun an experiment or derive a metric from existing measurements is normally `review`: workload may be low or medium while decision stakes are high. Route it to a narrow evidence review, not to broad planning or execution.

Use judgment rather than converting these signals into task cards, scores, gates, hashes, or a persistent state machine.

Before delegating, perform a lightweight dispatch pass. Reuse facts already present in the active context. When location is still needed, spend about 30 seconds by default and no more than about 60 seconds or 3--5 read-only lookups finding the relevant artifacts, terminology, and decision criteria. Do not duplicate the subagent's substantive investigation.

Answer directly when the task is bounded, the main dispatcher already has the decisive context, the answer should take about 90 seconds or less, and the user did not explicitly request this skill, delegation, or independent review.

## Delegate minimally

- Use one subagent by default.
- Add parallel subagents only for genuinely independent work that will materially reduce elapsed time.
- Keep at most one writer in a shared worktree. Read-only agents may run alongside the writer when they do not depend on an unstable artifact.
- Let the main dispatcher edit the returned result for clarity without collapsing material decisions, exact parameters, operational steps, validation, recovery, or acceptance criteria. Do not require JSON envelopes, task IDs, approval records, or mandatory independent review.

## Assemble an adaptive context handoff

- Before spawning, separate candidate context into: exact conversation evidence worth preserving, neutral artifact or environment facts, and material to exclude. Preserve user authority, definitions, accepted decisions, preferences, and decisive raw observations; exclude irrelevant discussion, hidden reasoning, unverified causal stories, and the main dispatcher's preferred answer.
- Choose `fork_turns` deliberately when the subagent tool exposes it. Use the smallest positive value when a contiguous block of recent turns contains essential context and has low contamination risk. Use `fork_turns: "none"` when artifacts already carry the task, relevant conversation is scattered or old, prior assistant conclusions would bias the review, or the user requests independence.
- Remember that `fork_turns` copies a recent contiguous window rather than arbitrary messages. Do not inherit many irrelevant turns merely to reach one older fact. Extract that fact into the capsule instead. Use `fork_turns: "all"` only when the conversation is short, nearly every turn is essential, and inherited assistant content does not compromise independence.
- Always supplement inherited or extracted conversation with a concise neutral capsule. Include the objective, authorized scope, selected user instructions or accepted decisions, verified facts, an evidence index, unresolved questions, decision criteria, deliverable, relevant domain skill, and stop condition.
- Prefer an evidence index such as file paths and line anchors, function names, experiment IDs, paper identifiers, equations, figure numbers, or saved result locations. Do not paste file contents that the subagent can read directly.
- Quote only the smallest conversation fragment whose exact wording matters. Label it as `User instruction`, `Accepted decision`, or `Observed output`; distinguish direct quotes from neutral paraphrases. Treat inherited assistant statements as navigation, not as evidence.
- Keep the added capsule compact, normally about 150--400 words excluding paths and necessary exact excerpts. Tell the subagent to verify decisive evidence and widen its reading only when the supplied index is insufficient; it must report that expansion rather than silently reconstructing the whole repository or discussion.

## Preserve substantial plans

- Treat a delegated plan as substantial when faithful delivery requires exact commands or configuration, several dependent stages, explicit recovery or acceptance criteria, multiple decision branches, or enough detail that a chat-only summary would omit execution-critical information.
- Save a substantial plan as Markdown when the user explicitly invoked this skill for planning, requested a saved plan, or otherwise authorized a plan artifact. Prefer the user's exact path. Otherwise resolve `<codex-home>` from the installed skill location and use `<codex-home>/agent-academic-squad/plans/<YYYY-MM-DD>/<HHMMSS>-<task-slug>.md`.
- Resolve `<codex-home>` as the parent of the `skills/` directory containing this installed skill; do not hardcode a host-specific home path. Create dated directories only when saving an authorized plan. Never overwrite an existing plan silently; use a new timestamp or an explicit revision suffix.
- Store the normalized final plan, not the subagent transcript or hidden reasoning. Preserve the objective, verified facts and source anchors, exact parameters, ordered dependencies, commands or configuration needed for execution, model assignments, unresolved decisions, validation, recovery, stop conditions, acceptance criteria, cost drivers, and the statement that execution has not started.
- Before replying, compare the saved plan with the subagent's final deliverable and restore any missing decision branch or execution-critical detail. Do not convert an unresolved choice into a default recommendation unless the user already authorized it.
- In chat, lead with the result and provide a clickable absolute path. Also state every unresolved user decision, the most material risks, and whether execution has started. The chat response may summarize details already preserved in the file, but it must remain sufficient for the user to decide whether to approve execution.
- When saving is not authorized or the path is not writable, return the faithful plan in chat instead of compressing it, and report the unsaved status.

## Return useful handoffs

For a plan, return:

- objective and deliverables;
- ordered work and dependencies;
- proposed model for each executed part;
- rough time or cost drivers;
- material risks and decisions;
- the saved-plan path when a plan artifact was created;
- a clear statement that execution has not started.

For completed execution, return:

- the outcome first;
- artifacts or changed files;
- checks or experiment evidence actually produced;
- unresolved limitations;
- what the user may accept, revise, or send for review.

For review, return prioritized findings with evidence and a recommendation. Do not add a second reviewer unless the user asks or the review itself contains independent, parallel components.

## Handle waits and failures

- Treat a wait-window timeout as an observation, not a task failure. Continue waiting when the subagent is still running.
- Retry a clearly transient tool, network, or malformed-response failure once.
- Do not diagnose environment, permission, or network failures as model weakness.
- When the default route fails because of demonstrated capability limits, move one permitted effort step upward and disclose it.
- When the user specified the exact model or effort, do not change it after failure without the user's permission.
- Stop and return the partial result when execution discovers a material scope expansion, missing authority, or an invalid plan.

## Keep the workflow lightweight

Do not create governance state, task cards, approval gates, hashes, transition logs, acceptance packets, or a standing hierarchy. The durable object is the user's task and its artifacts; subagents are temporary helpers selected for that task.
