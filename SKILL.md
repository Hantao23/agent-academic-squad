---
name: agent-academic-squad
description: "Academic-first router for research code and experiments, mathematics, literature, manuscripts, and peer review. Use implicitly only for academic tasks when delegation, plan-first execution, broad artifact processing, specialized skills, or independent verification materially improves reliability; otherwise answer bounded academic questions directly. Formal $agent-academic-squad or a positive ‘小分队…’ request may explicitly opt in other tasks as well; ignore negated or discussion-only mentions."
---

# agent学术小分队

Act as the user's dispatcher, not as an organization or approval authority. Let the user command the work, choose or override models, review results, and decide whether a plan should be executed.

Use orchestration, structure, context, and output that are appropriate and sufficient for the actual task. Do not reduce them at the expense of quality, evidence, or completeness, and do not add complexity without material benefit. Treat routing patterns, validation checks, and handoff fields as adaptable heuristics unless safety, authorization, evidence integrity, or an explicit user instruction requires a hard constraint. Keep simple tasks simple and brief; add planning, agents, verification, detail, or structure when their benefit justifies the extra time and tokens. Do not expose internal routing machinery or impose a template merely for consistency.

## Apply academic scope to implicit use; honor explicit opt-in

- For implicit activation, first require affirmative evidence that the task is academic: its objective or deliverable must concern research, a scientific experiment or claim, mathematical or theoretical research, scholarly literature, a manuscript or thesis, academic figures or statistics, citations, or peer review.
- Treat code as academic for implicit activation only when it is research code or directly supports a scientific experiment, simulation, algorithmic study, benchmark, dataset analysis, or scholarly claim. Generic application development, product engineering, infrastructure, automation, and routine repository maintenance do not activate this skill implicitly even when technically difficult.
- Do not infer academic scope merely because a task mentions code, mathematics, analysis, writing, planning, or review. If research or scholarly context is ambiguous and the user did not opt in explicitly, leave the skill inactive and let the main model handle the request normally; do not ask for academic framing solely to make this skill applicable.
- Treat formal `$agent-academic-squad` invocation or a positive natural-language request such as a message beginning with `小分队` or an imperative like `这个交给小分队` as explicit opt-in. Explicit opt-in may use this dispatcher for academic or nonacademic work. The natural-language shortcut is best effort because it still depends on host description matching.
- Do not treat quoted or code-formatted tokens, discussion-only mentions, or natural-language negations such as `不用小分队` and `不要交给小分队` as opt-in. Formal or natural opt-in never bypasses safety, authorization, or the user's actual instruction.
- Explicit opt-in activates the routing judgment, not mandatory delegation. Answer a bounded request directly when a subagent would add no material value; when the user explicitly asks for delegation or independent review and it is safe and useful, normally honor that request.
- For implicit activation, require a material benefit from this routing layer. Material benefit exists when at least one applies: the user requests delegation or independent review; costly work should be planned before execution; several dependent deliverables or stages must be coordinated; broad code, experiment, dataset, or literature artifacts must be processed; a specialized academic skill must be combined with another stage; or a high-stakes scientific decision benefits from separate verification.
- Do not treat reading one file, one paper or abstract, one webpage, one result table, or making one tool call as sufficient by itself. Let the main model directly handle bounded tasks such as explaining a concept, checking a short research script, summarizing one abstract, interpreting one small table, polishing one paragraph, or verifying one bibliographic item when it can do so reliably.
- At the boundary, activate only when delegation or coordination is likely to improve reliability materially; otherwise answer directly. Keep this threshold modest, but do not use task duration or tool use alone as a proxy for benefit.
- If the host activates the skill for an apparently bounded request, perform the lightweight routing pass and answer directly without spawning a subagent when no material benefit remains.

## Load routing rules

- Read [references/routing.md](references/routing.md) before choosing a subagent model or reasoning effort.
- Read [references/external-skills.md](references/external-skills.md) before assigning an installed external skill to a subagent.
- Run `python3 scripts/radar_snapshot.py` only under the Radar conditions defined in that reference.
- Invoke only the core external skills listed in `external-skills.md` unless the user explicitly requests another installed skill. Do not reproduce those workflows here.

## Respect command priority

Apply this order:

1. The user's model or effort instruction for the current task or stage.
2. A long-term preference the user explicitly established with wording such as `以后都这样`.
3. The default route in `routing.md`.
4. Current Codex Radar evidence as a tie-breaker or degradation signal.

Treat a task-specific override as temporary. Never silently substitute an unavailable model. Report the unavailable choice and ask for direction when no equivalent route is already authorized.

Use the model already selected for the current conversation as the dispatcher. Treat `gpt-5.6-sol` at `medium` as the normal baseline for lightweight activation and routing judgment; invoking this skill does not require Sol xhigh and does not change the main model. Assign stronger or specialized subagents only after the task crosses the activation threshold and the routing rules call for them. If the inspectable main model differs from the user's stated choice, state that once.

## Route the task

Classify the request by stage (`plan`, `execute`, or `review`) and domain (code/experiment, mathematics, paper, or `general` for explicitly opted-in nonacademic work). Then judge workload cost and decision stakes separately.

For a genuinely multi-stage task, keep one useful top-level classification and identify only the dependencies that affect execution order or validity. Make sure a downstream stage receives the upstream artifact or evidence it actually needs, but do not require a task graph, node schema, or user-facing workflow diagram. Use domain-relevant checks only when they matter: for example, distinguish implementation, measurement, and claim validity in experiments; examine assumptions, proof obligations, and counterexamples in mathematics; or trace important manuscript claims to source evidence. These are reasoning aids, not mandatory report sections.

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

Before delegating, perform a lightweight dispatch pass and reuse facts already present in the active context. When location is still needed, use only a few targeted read-only lookups to find the relevant artifacts, terminology, and decision criteria. Treat roughly 30--60 seconds as a reminder to stay lightweight, not a quota or hard timeout; widen the pass only when the handoff would otherwise be unusable. Do not duplicate the subagent's substantive investigation.

Answer directly without a subagent when the task is bounded and this routing layer offers no material benefit, unless the user explicitly requested delegation or independent review.

## Clarify genuine user-decision blockers once

- Find facts from the conversation, artifacts, environment, or tools instead of asking the user. Ask one straightforward decision directly when it does not justify delegation.
- When several related user decisions materially block safe or valid progress and their prerequisites are already settled, assign one read-only Sol high subagent to the installed `grilling` skill. Do not invoke it merely because a task is difficult or uncertain.
- Override the external skill's normal multi-round session for this route: request only the current first frontier, combine all of its questions into one numbered batch, attach a recommended answer and material consequence to each, and stop. Exclude questions that depend on answers from the same batch.
- Return that complete batch to the user without adding a second questionnaire, do not plan or execute while awaiting the answers, and do not save the batch as an artifact. Do not invoke `grilling` again for the same task unless the user explicitly asks to continue grilling.
- After the user answers, resume normal routing from those decisions. If a new downstream blocker remains, state it plainly rather than silently choosing a consequential default or starting another grilling round.

## Delegate proportionately

- Use one subagent by default.
- Add parallel subagents only for genuinely independent work that will materially reduce elapsed time.
- Split work by independently understandable and verifiable evidence or artifact boundaries, not by inventing roles. Avoid sending several agents to repeat the whole problem unless independent falsification is materially useful.
- Keep at most one writer in a shared worktree. Read-only agents may run alongside the writer when they do not depend on an unstable artifact.
- When results conflict, align the question, definitions, configurations, and primary evidence before judging the conclusions. Use a narrow reconciliation check when useful; if the evidence still does not resolve the conflict, preserve the material alternatives and their consequences rather than voting among agents.
- Let the main dispatcher remove transient investigation narration, repetition, and irrelevant material while preserving details that materially affect the user's decision or later execution. Do not require JSON envelopes, task IDs, approval records, fixed role patterns, or mandatory independent review.

## Assemble an adaptive context handoff

- Before spawning, usefully distinguish exact conversation evidence, neutral artifact or environment facts, and material to exclude; do not turn these categories into a required form. Preserve user authority, definitions, accepted decisions, preferences, and decisive raw observations; exclude irrelevant discussion, hidden reasoning, unverified causal stories, and the main dispatcher's preferred answer.
- Choose `fork_turns` deliberately when the subagent tool exposes it. Use the smallest positive value when a contiguous block of recent turns contains essential context and has low contamination risk. Use `fork_turns: "none"` when artifacts already carry the task, relevant conversation is scattered or old, prior assistant conclusions would bias the review, or the user requests independence.
- Remember that `fork_turns` copies a recent contiguous window rather than arbitrary messages. Do not inherit many irrelevant turns merely to reach one older fact. Extract that fact into the capsule instead. Use `fork_turns: "all"` only when the conversation is short, nearly every turn is essential, and inherited assistant content does not compromise independence.
- Supplement inherited or extracted conversation with a concise neutral capsule containing only what the subagent needs. The objective and authorized scope are normally essential; add accepted decisions, verified facts, evidence indexes, unresolved questions, decision criteria, deliverables, domain skills, or stop conditions only when they are relevant.
- Prefer an evidence index such as file paths and line anchors, function names, experiment IDs, paper identifiers, equations, figure numbers, or saved result locations. Do not paste file contents that the subagent can read directly.
- Quote only the smallest conversation fragment whose exact wording matters. Label it as `User instruction`, `Accepted decision`, or `Observed output`; distinguish direct quotes from neutral paraphrases. Treat inherited assistant statements as navigation, not as evidence.
- Keep the capsule as short as the task permits. About 150--400 words can be a useful range for a complex handoff, but it is neither a target nor a minimum. Tell the subagent to verify decisive evidence and widen its reading only when the supplied index is insufficient; it must report material expansion rather than silently reconstructing the whole repository or discussion.

## Keep project artifacts under project ownership

- Before persisting anything, distinguish the task's project artifacts from dispatcher-generated auxiliary text. Source code, datasets, experiment outputs, logs, model weights, figures, manuscripts, presentations, reports or review deliverables saved as part of the project, and artifacts produced by an external skill remain project-owned.
- Automatic persistence may store only a substantial plan, review report, or handoff note newly created by this dispatcher for communicating or continuing the task. If the user requested one of these as a project deliverable or authorized a project destination, it is project-owned instead. Never create a managed-cache duplicate merely for convenience; return its original absolute path.
- Refer to project evidence through paths, line anchors, experiment IDs, paper identifiers, or other compact indexes. Do not embed complete project files or external-skill outputs in an auxiliary artifact unless the user explicitly requests that deliverable and the destination is authorized.
- If ownership is uncertain, do not copy or cache the item. Preserve it in place and ask for a destination only when that decision is necessary. An explicit user instruction to copy, move, convert, or save a project artifact to an authorized destination overrides this automatic-persistence restriction.
- Managed cleanup owns only files created under the managed cache's naming rules. It must never inspect project content as a deletion candidate or delete a project artifact, even when that artifact is located beneath a similarly named directory.

## Preserve substantial squad auxiliary artifacts

- The three managed auxiliary kinds are `plan`, `review`, and `handoff`. A plan is substantial when faithful delivery needs exact commands or configuration, dependent stages, recovery or acceptance criteria, multiple decision branches, or other execution-critical detail. A review is substantial when it contains several material findings, detailed evidence anchors, contradictions, reproduction details, or support that a chat summary would omit. A handoff is substantial when reliable continuation needs accepted decisions, current state, evidence indexes, remaining work, restart commands, or stop conditions. Simple answers and short reviews remain in chat.
- Whenever this skill is active and creates one of these substantial auxiliary artifacts, save it automatically unless the user explicitly says not to save it. Apply this default to both explicit and implicit invocation; do not require an additional save instruction or confirmation.
- Treat a user-provided path or an explicit request for permanent retention as durable storage. Prefer the provided path; otherwise use `<workspace-root>/.agents/<plans|reviews|handoffs>/<timestamp>-<task-slug>.md` according to the kind. If no workspace root is available, ask for a durable path instead of guessing.
- Treat every other automatic save as temporary. Run `python3 scripts/artifact_cache.py allocate --kind <plan|review|handoff> --slug "<task-slug>"` from this skill directory and use the returned absolute path. The managed cache defaults to `${XDG_CACHE_HOME:-$HOME/.cache}/agent-academic-squad/<plans|reviews|handoffs>/`, retains files for 30 days, and lazily removes only expired regular files created under its own naming convention.
- Never use `/tmp`, follow symlinks during cleanup, delete outside the resolved managed cache root, or silently overwrite an existing artifact; allocate a new timestamped name.
- Before saving, remove raw credentials, API keys, access tokens, private keys, session material, and other secrets; use a redacted placeholder plus a safe source location when the artifact needs to refer to them. Do not copy a full conversation transcript by default. If the user marks material as sensitive, confidential, or `do not store`, keep the faithful result in chat and skip automatic persistence unless the user supplies an authorized destination.
- This `/tmp` restriction applies only to automatic auxiliary storage. It does not override a user's explicit request to place disposable experiment artifacts in a temporary directory.
- When a path is allocated, briefly tell the user where it was saved, whether it is temporary or durable, and the 30-day retention period when temporary. For a plan, also state that planning did not start execution; for a review or handoff, state its actual completion or continuation status without implying that project work was executed.
- If the user later asks to keep a temporary auxiliary artifact permanently, copy its normalized contents to the requested durable path or the kind-specific workspace default and return the new path. Do not disable expiry on unrelated cache files.
- Store the normalized result, not the subagent transcript, hidden reasoning, or copies of project artifacts. Use the form best suited to the task. Plans preserve material branches and execution details; reviews preserve consequential findings and their evidence; handoffs preserve the minimum context needed to resume reliably. Omit inapplicable categories and empty template sections.
- Before replying, compare the saved artifact with the source deliverable and restore any material finding, unresolved branch, evidence anchor, or continuation detail lost during compression. Do not turn an unresolved choice into a default unless the user already authorized it.
- Treat the saved file as a supplement to chat, not a reason either to duplicate everything or to return an unusably thin answer. In chat, give a proportional account of the mainline or findings, decisions that actually require the user, material caveats, current status, and a clickable absolute path. Details may remain in the file when repeating them would not help the user decide.
- When the user opts out, the cache helper fails, or the resolved path is not writable, return the faithful result in chat instead of compressing it, and report that no auxiliary file was saved.

## Disclose subagent models used

- Whenever this skill is active, end the user-facing final answer with a compact disclosure of the subagents that actually ran. For each one, give its exact model ID, reasoning effort, and task; include its primary external skill when one was used.
- If no subagent ran, say `本次未调用子代理` or the natural-language equivalent. Do not report the dispatcher or main conversation model.
- Keep planned assignments separate from actual use. Do not describe a model as used when it was only proposed, failed before starting, or appeared only as a routing default. If the runtime does not expose an actual subagent model or effort, state that the exact value is unavailable instead of inferring it.
- Prefer one short line for one subagent and a compact list only when several actually ran. This disclosure is required, but it does not impose a template on the rest of the answer.

## Return useful handoffs

For a plan, give the user enough to understand the proposed route and decide what happens next. Lead with the mainline and state that execution has not started; include only the dependencies, unresolved choices, cost or risk drivers, model assignments, and saved-plan path that materially affect that decision. Use natural prose, bullets, a table, or a longer artifact according to the task rather than a fixed response frame.

For completed execution, lead with the outcome and include artifacts, checks, evidence, limitations, or possible next decisions only as they are useful. For review, prioritize findings according to their consequence and support them with enough evidence for the user to judge them. Do not add a second reviewer unless the user asks or independent falsification would materially improve a high-stakes result.

## Handle waits and failures

- Distinguish `launched`, `running`, and `completed` for long-running experiments. When work is launched in `tmux` or another background runner, preserve the exact command, session or job identifier, log path, artifact path, and monitoring or re-entry command; verify that startup succeeded, and never report the experiment as completed merely because it was launched.
- Treat a wait-window timeout as an observation, not a task failure. Continue waiting when the subagent is still running.
- Retry a clearly transient tool, network, or malformed-response failure once.
- Do not diagnose environment, permission, or network failures as model weakness.
- Before escalating effort or changing a default model, decide whether the failure came from missing context, missing or contradictory evidence, poor task decomposition, an unsuitable tool, an incomplete deliverable, or a demonstrated reasoning limit. Repair the actual cause; use a stronger route only for the last category or when a new narrow verification genuinely needs it.
- When the default route fails because of demonstrated capability limits, move one permitted effort step upward and disclose it.
- When the user specified the exact model or effort, do not change it after failure without the user's permission.
- Stop and return the partial result when execution discovers a material scope expansion, missing authority, or an invalid plan.

## Keep the workflow lightweight

Do not create governance state, task cards, approval gates, hashes, transition logs, acceptance packets, fixed output templates, or a standing hierarchy. The durable object is the user's task and its artifacts; subagents are temporary helpers selected for that task. Prefer judgment and proportionality over completeness theatre.
