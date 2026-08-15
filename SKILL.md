---
name: agent-academic-squad
description: "Academic router for research code and experiments, mathematics, literature, manuscripts, and peer review. Use implicitly only when delegation, plan-first execution, broad artifact processing, specialized academic skills, or independent verification materially improves reliability; otherwise answer bounded academic questions directly. Formal invocation: $agent-academic-squad. Treat ‘小分队…’ as a best-effort natural-language shortcut; ignore negated shortcuts or discussion-only natural-language mentions."
---

# agent学术小分队

Act as the user's dispatcher, not as an organization or approval authority. Let the user command the work, choose or override models, review results, and decide whether a plan should be executed.

## Apply the academic gate, then activate on demand

- Before any complexity judgment, require affirmative evidence that the task is academic: its objective or deliverable must concern research, a scientific experiment or claim, mathematical or theoretical research, scholarly literature, a manuscript or thesis, academic figures or statistics, citations, or peer review.
- Treat code as academic only when it is research code or directly supports a scientific experiment, simulation, algorithmic study, benchmark, dataset analysis, or scholarly claim. Generic application development, product engineering, infrastructure, automation, and routine repository maintenance are outside this skill even when technically difficult.
- Do not infer academic scope merely because a task mentions code, mathematics, analysis, writing, planning, or review. If research or scholarly context is ambiguous, leave the skill inactive and let the main model handle the request normally; do not ask for academic framing solely to make this skill applicable.
- Explicit `$agent-academic-squad` invocation is the formal Codex override and activates the skill wherever the host recognizes it; prose negation around the formal token is not a reliable bypass. `小分队...` is only a best-effort natural-language shortcut that still depends on implicit description matching; once matched, treat a message beginning with `小分队` or an imperative such as `这个交给小分队` as the same user authority. Do not activate the shortcut for natural-language negations such as `不用小分队`, `不要交给小分队`, or discussion-only mentions. Otherwise, delegation, planning, execution, review, or model-assignment wording activates it only after the academic gate passes.
- For implicit activation, require a material benefit from this routing layer. Material benefit exists when at least one applies: the user requests delegation or independent review; costly work should be planned before execution; several dependent deliverables or stages must be coordinated; broad code, experiment, dataset, or literature artifacts must be processed; a specialized academic skill must be combined with another stage; or a high-stakes scientific decision benefits from separate verification.
- Do not treat reading one file, one paper or abstract, one webpage, one result table, or making one tool call as sufficient by itself. Let the main model directly handle bounded tasks such as explaining a concept, checking a short research script, summarizing one abstract, interpreting one small table, polishing one paragraph, or verifying one bibliographic item when it can do so reliably.
- At the boundary, activate only when delegation or coordination is likely to improve reliability materially; otherwise answer directly. Keep this threshold modest, but do not use task duration or tool use alone as a proxy for benefit.
- If the host activates the skill for an apparently bounded request, perform the lightweight routing pass and answer directly without spawning a subagent when no material benefit remains.

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

Use the model already selected for the current conversation as the dispatcher. Treat `gpt-5.6-sol` at `medium` as the normal baseline for lightweight activation and routing judgment; invoking this skill does not require Sol xhigh and does not change the main model. Assign stronger or specialized subagents only after the task crosses the activation threshold and the routing rules call for them. If the inspectable main model differs from the user's stated choice, state that once.

## Route the task

Classify the request by stage (`plan`, `execute`, or `review`) and domain (code/experiment, mathematics, or paper). Then judge workload cost and decision stakes separately.

- For an explicit planning request, delegate planning, return the plan, and stop. Do not execute it in the same turn.
- For an execution request with a previously accepted plan, execute that plan without replanning unless it is stale, impossible, or missing a decision that materially changes the result.
- For an execution-looking request without a prior plan, first decide whether the request itself is an accepted executable specification. A concrete target plus a named reference protocol or fixed parameters, authorized artifact scope, and no material unresolved choice is enough; execute it even when runtime is long. Otherwise execute directly when manageable, but delegate planning and stop when workload is high or a missing choice would materially change the experiment.
- For an explicit `直接执行` or `不要规划` instruction, execute directly within the user's authorized scope even when the default would plan first.
- For review, inspect and report only. Do not modify the reviewed artifact unless the user also asks for changes. Before broad evidence extraction, fix the decisive criterion and distinguish final outcomes from intermediate diagnostics; then check coverage and contradictions before summarizing.

Treat workload as high when any of these applies:

- It will probably take more than about 20 minutes of agent or experiment time.
- It requires several experiment rounds, broad repository investigation, or large-scale literature processing.
- It has multiple dependent deliverables or would benefit from more than one subagent.
- It requires expensive computation or substantial external mutation.

Treat decision stakes as high when a wrong answer could materially affect a scientific claim, trigger an unnecessary costly rerun, invalidate an experiment or proof, damage an important artifact, or cause a difficult-to-reverse action. High stakes require stronger verification or a stronger review route; they do not by themselves make the workload high or justify a cold, repository-wide investigation.

A bounded recommendation about whether to rerun an experiment or derive a metric from existing measurements is normally `review`: workload may be low or medium while decision stakes are high. Route it to a narrow evidence review, not to broad planning or execution.

Use judgment rather than converting these signals into task cards, scores, gates, hashes, or a persistent state machine.

Before delegating, perform a lightweight dispatch pass. Reuse facts already present in the active context. When location is still needed, spend about 30 seconds by default and no more than about 60 seconds or 3--5 read-only lookups finding the relevant artifacts, terminology, and decision criteria. Do not duplicate the subagent's substantive investigation.

Answer directly without a subagent when the academic task is bounded and this routing layer offers no material benefit, unless the user explicitly requested delegation or independent review.

## Delegate minimally

- Use one subagent by default.
- Add parallel subagents only for genuinely independent work that will materially reduce elapsed time.
- Keep at most one writer in a shared worktree. Read-only agents may run alongside the writer when they do not depend on an unstable artifact.
- Let the main dispatcher edit the returned result only to remove transient investigation or reasoning narration, exact repetition, and demonstrably irrelevant material. When in doubt, retain the content. Never remove an unresolved branch, exact parameter, dependent step, command, artifact path, validation, recovery or stop condition, acceptance criterion, cost driver, material risk, or model assignment. Do not require JSON envelopes, task IDs, approval records, or mandatory independent review.

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
- Whenever this skill is active and classifies a planning result as substantial, save the final plan automatically unless the user explicitly says not to save it. Apply this default to both explicit and implicit skill invocation; do not require an additional save instruction or confirmation.
- Treat a user-provided path or an explicit request to save, retain, or keep the plan permanently as durable storage. Prefer the provided path; otherwise use `<workspace-root>/.agents/plans/<timestamp>-<task-slug>.md`. If no workspace root is available, ask for a durable path instead of guessing.
- Treat every other automatic save as temporary. Run `python3 scripts/plan_cache.py allocate --slug "<task-slug>"` from this skill directory and use the returned absolute path. The managed cache defaults to `${XDG_CACHE_HOME:-$HOME/.cache}/agent-academic-squad/plans/`, retains plans for 30 days, and lazily removes only expired regular files created under its own naming convention.
- Never use `/tmp`, never follow symlinks during cleanup, and never delete outside the resolved managed cache root. Never overwrite an existing plan silently; allocate a new timestamped name.
- This `/tmp` restriction applies only to automatic plan storage. It does not override a user's explicit request to place disposable experiment artifacts in a temporary directory.
- As soon as the task is classified as a substantial plan, tell the user that automatic saving is enabled, give the planned absolute path, state whether it is temporary or durable, disclose the 30-day retention period for temporary plans, and restate that planning does not start execution. Do not wait until the final response to disclose the artifact.
- If the user later asks to keep a temporary plan permanently, copy its normalized contents to the requested durable path or the workspace default and return the new path. Do not disable expiry on unrelated cache files.
- Store the normalized final plan, not the subagent transcript or hidden reasoning. Preserve the objective, verified facts and source anchors, exact parameters, ordered dependencies, commands and configuration needed for execution, all input and output artifact paths, model assignments, every unresolved decision branch, validation, recovery, stop conditions, acceptance criteria, cost drivers, the complete material-risk list, and the statement that execution has not started.
- Use these sections in every saved substantial plan, in this order and localized to the user's language: `Conclusion summary`; `Decisions required from the user`; `Verified facts and sources`; `Complete executable plan`; `Parameters, commands, and artifact paths`; `Validation, recovery, and stop conditions`; `Cost, risks, and model assignments`; `Execution status`. Keep the decisions section even when empty and state `None` explicitly.
- Before replying, compare the saved plan with the subagent's final deliverable and restore any missing decision branch or execution-critical detail. Preserve all unresolved alternatives in both the file and chat; do not present only the recommended route or convert an unresolved choice into a default unless the user already authorized it.
- Treat the plan file as a supplement to chat, never as a substitute. Even when a file exists, the chat response must include a self-contained description of the entire plan mainline in dependency order, every decision still required from the user with the options and consequences, the most material risks, the execution status, and a clickable absolute path. The mainline may be paraphrased rather than copied verbatim, but it must let the user understand the approach and decide whether to proceed without opening the file.
- Detailed commands, long configuration blocks, and large validation tables may live primarily in the file only after their role and place in the mainline have been explained in chat. Do not shorten the chat merely because a file was created.
- When the user opts out, the cache helper fails, or the resolved path is not writable, return the faithful plan in chat instead of compressing it, and report that no plan file was saved.

## Return useful handoffs

For a plan, return:

- objective, deliverables, and a self-contained description of the entire plan mainline;
- ordered work and dependencies;
- every unresolved user decision with options and consequences;
- proposed model for each executed part;
- rough time or cost drivers;
- the complete material-risk list;
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

- Distinguish `launched`, `running`, and `completed` for long-running experiments. When work is launched in `tmux` or another background runner, preserve the exact command, session or job identifier, log path, artifact path, and monitoring or re-entry command; verify that startup succeeded, and never report the experiment as completed merely because it was launched.
- Treat a wait-window timeout as an observation, not a task failure. Continue waiting when the subagent is still running.
- Retry a clearly transient tool, network, or malformed-response failure once.
- Do not diagnose environment, permission, or network failures as model weakness.
- When the default route fails because of demonstrated capability limits, move one permitted effort step upward and disclose it.
- When the user specified the exact model or effort, do not change it after failure without the user's permission.
- Stop and return the partial result when execution discovers a material scope expansion, missing authority, or an invalid plan.

## Keep the workflow lightweight

Do not create governance state, task cards, approval gates, hashes, transition logs, acceptance packets, or a standing hierarchy. The durable object is the user's task and its artifacts; subagents are temporary helpers selected for that task.
