# Agent Academic Squad

**English** | [简体中文](README.zh-CN.md)

A lightweight Codex skill for routing academic tasks.

It activates only for clearly academic work and only when routing is likely to provide material value. It first checks whether the request concerns research, scientific experiments, mathematics or algorithms, scholarly literature, or manuscript work. Reading one file or webpage, or making one tool call, is not enough by itself; the squad becomes useful when the task needs planning, coordination, broad artifact processing, specialized academic skills, or independent review.

## What it solves

Academic work usually falls into three domains:

- **Code and experiments:** planning, implementation, debugging, experiment design, and execution;
- **Mathematics and algorithms:** formula checks, strategy analysis, algorithm construction, and formal proof;
- **Paper work:** literature search, full-text reading, writing, polishing, citations, peer review, and reviewer responses.

These tasks need different models, reasoning effort, and context. This skill separates planning from execution or review, and evaluates two dimensions independently:

- **Workload cost:** expected time, computation, and context;
- **Decision stakes:** whether an incorrect conclusion could affect a scientific claim, trigger an unnecessary rerun, or damage an important artifact.

High-cost work is normally planned first unless the user has already supplied and authorized an executable specification. Bounded work can go directly to the appropriate executor.

## How it works

```mermaid
flowchart TD
    A["User submits a task"] --> B["Main model performs lightweight triage"]
    B --> C["Identify stage: plan / execute / review"]
    B --> D["Identify domain: code-experiment / mathematics / paper"]
    C --> E["Assess workload and decision stakes separately"]
    D --> E
    E --> F{"Can the task be handled directly?"}
    F -- "Yes" --> G["Main model answers or delegates one executor"]
    F -- "High cost and no accepted plan" --> H["Delegate a planner and return the plan"]
    H --> I["User decides whether to execute"]
    I --> G
    G --> J["Return results, evidence, and artifacts for user review"]
```

Core principles:

- Academic scope is a hard gate. Generic software engineering, business operations, everyday writing, personal tasks, and general questions do not implicitly activate the skill.
- Words such as “code,” “mathematics,” “analysis,” “writing,” “planning,” or “review” do not prove academic scope.
- Implicit activation is supported. A conversation running `GPT-5.6 Sol medium` can perform the lightweight dispatch check; the main model does not need to be switched to xhigh first.
- A single file, abstract, short script, small table, paragraph edit, or one tool call is not sufficient unless delegation would materially improve reliability.
- User-selected models and reasoning effort always override defaults.
- One subagent is the default. Parallel agents are used only for genuinely independent work.
- The dispatcher selects relevant conversation context and adds neutral, verifiable artifact and evidence indexes instead of copying the entire conversation.
- Substantial plans are saved automatically as complete Markdown artifacts. The chat still explains the mainline and unresolved decisions.
- A planning request returns a plan and stops. It does not silently start execution.
- A review request reports findings and does not modify artifacts unless the user also asks for changes.
- Small tasks are answered directly; the skill does not use multiple agents for their own sake.

See [`SKILL.md`](SKILL.md) for the complete workflow and [`references/routing.md`](references/routing.md) for model selection.

## Plan artifacts

When the squad produces a substantial plan, it saves the plan automatically for both implicit and explicit activation. The user can opt out by saying not to save it.

Automatic saving has two modes:

- Without an explicit request for permanent retention, the plan goes into a managed cache with a default 30-day lifetime.
- If the user asks to save, retain, or keep the plan permanently, or supplies a path, the plan is stored durably.
- A temporary plan can be copied to durable storage before expiry.
- The dispatcher immediately reports the absolute path, temporary or durable status, retention period, and that planning has not started execution.

The default temporary cache is:

```text
${XDG_CACHE_HOME:-$HOME/.cache}/agent-academic-squad/plans/
```

`scripts/plan_cache.py` performs lazy cleanup when allocating a new path. It deletes only ordinary files older than 30 days that match its own naming convention. It does not use `/tmp`, follow symlinks, or delete outside its managed cache root. A permanent plan without a user-supplied path is stored under `.agents/plans/` in the current workspace.

Every saved substantial plan contains these sections:

1. Conclusion summary
2. Decisions required from the user
3. Verified facts and sources
4. Complete executable plan
5. Parameters, commands, and artifact paths
6. Validation, recovery, and stop conditions
7. Cost, risks, and model assignments
8. Execution status

The dispatcher may remove investigation narration, exact repetition, and demonstrably irrelevant material. It must preserve unresolved branches, parameters, dependencies, commands, artifact paths, acceptance criteria, costs, risks, and model assignments.

The plan file supplements the chat; it never replaces it. Even when a file is saved, the response must describe the full execution mainline, all unresolved user decisions and their consequences, material risks, execution status, and the absolute file path. Long commands and tables may live primarily in the file only after their role is explained in chat.

## Default model routing

Defaults are recommendations, not restrictions:

| Work | Default route |
| --- | --- |
| Short or standard planning | Sol medium / high |
| High-cost or cross-module planning | Sol xhigh |
| Normal multi-file development, hard diagnosis, or code review | Sol xhigh |
| Execute a fixed, testable experiment protocol | Luna max |
| Mathematical strategy or algorithm construction | Sol xhigh |
| Formal proof or difficult derivation | Sol max |
| Broad literature search and first-pass screening | Luna max |
| Full-paper reading and long-source evidence extraction | Terra max |
| Core manuscript writing, restructuring, or submission-level review | Sol xhigh |

Exact model IDs, escalation conditions, and Codex Radar rules are defined in [`references/routing.md`](references/routing.md). The skill never silently replaces a model explicitly selected by the user.

## Installation

Current Codex documentation recommends `$HOME/.agents/skills` for user-level skills and `.agents/skills` for repository-level skills:

```bash
git clone https://github.com/Hantao23/agent-academic-squad.git "$HOME/.agents/skills/agent-academic-squad"
```

```bash
git clone https://github.com/Hantao23/agent-academic-squad.git .agents/skills/agent-academic-squad
```

Some Codex Desktop and older Codex environments still discover user skills from `$CODEX_HOME/skills`, normally `~/.codex/skills`:

```bash
git clone https://github.com/Hantao23/agent-academic-squad.git "${CODEX_HOME:-$HOME/.codex}/skills/agent-academic-squad"
```

Restart Codex, or start a new task so the skill catalog is refreshed.

This skill requires a Codex environment that supports subagent delegation. `scripts/radar_snapshot.py` uses only the Python 3 standard library and accesses the public Codex Radar feeds only when current model evidence could change a routing decision.

## Evals

`evals/trigger-routing.csv` contains 41 formal, shortcut, implicit, negative, contextual, and boundary cases. `evals/e2e-cases.json` adds 15 core cases for planned versus runtime routes, allowed versus required models and efforts, subagent bounds, writes, final states, forbidden actions, unavailable-model handling, single-writer behavior, user overrides, and temporary artifacts. A separate two-case `evals/nature-integration-cases.json` suite tests real external Nature Skill invocation without making ordinary E2E depend on those installations. The datasets contain generalized examples derived from real usage, but no original task transcript or private path.

Run deterministic validation and unit tests with:

```bash
python3 scripts/validate_eval_cases.py
python3 -m unittest discover -s tests -v
python3 scripts/run_e2e_evals.py --dry-run --max-cases 3
python3 scripts/run_e2e_evals.py --manifest evals/nature-integration-cases.json --dry-run
```

Run real, isolated JSONL smoke evals only when the Codex CLI has valid credentials:

```bash
python3 scripts/run_e2e_evals.py \
  --case e2e-direct-bounded-academic \
  --case e2e-implicit-plan \
  --case e2e-four-directory-read-only-review
```

The runner copies the current skill into an isolated repository-level skill directory, uses `--json --ephemeral --ignore-user-config --ignore-rules --output-schema`, applies the least sandbox declared by each case, redacts API-key-shaped strings, and stores ignored traces, structured receipts, and summaries under `evals/results/`. Its workspace snapshots compare the full path union and detect creation, modification, deletion, type changes, mode changes, and symlink-target changes—including changes inside the copied Skill. The four-directory review uses real fixture files rather than embedding all evidence in the prompt.

Results are `pass`, `fail`, or `inconclusive`. Required evidence that the current JSONL surface does not expose can never become a pass. The structured receipt describes the model's claimed stage, routes, agents, actions, and final state, but is explicitly self-report: it is checked alongside JSONL events, commands, and workspace changes and cannot alone prove task completion. Use `--strict` to make either `fail` or `inconclusive` return nonzero. Every summary records the Codex version, runner commit and hash, manifest hash, platform, and Python version.

Add `--strict-isolation` when `CODEX_API_KEY` is available to use clean temporary `HOME` and `CODEX_HOME` directories and exclude other user skills. The runner removes ambient OpenAI key variables and passes only `CODEX_API_KEY` to each `codex exec` subprocess. Authentication, network, missing external skills, and timeout failures are reported separately from Skill behavior.

Run the optional Nature integration suite only when the external skills are installed:

```bash
python3 scripts/run_e2e_evals.py \
  --manifest evals/nature-integration-cases.json \
  --external-skill-root "$HOME/.agents/skills" \
  --strict
```

`.github/workflows/ci.yml` runs deterministic validation on every push and pull request. `.github/workflows/e2e.yml` is manual, requires the repository `OPENAI_API_KEY` secret, exposes it as `CODEX_API_KEY` only to the E2E runner step, and lets a maintainer select either three representative cases or all 15 core cases. It uploads redacted artifacts for 14 days. Checkout, setup, dependency installation, and artifact upload steps cannot read the key. Dataset validation and dry runs are not presented as real model evaluations.

## Usage

As a best-effort natural-language shortcut, start the message with `小分队` (“squad”). A colon, comma, or space is optional. This shortcut still depends on Codex matching the skill description; `$agent-academic-squad` is the formal explicit invocation syntax.

```text
小分队帮我审查这三个实验目录，按测序深度输出表格。
```

```text
这个交给小分队，只规划，不执行。
```

Natural-language negations such as `不用小分队` or `不要交给小分队`, and sentences that merely discuss the name, do not trigger the shortcut. By contrast, `$agent-academic-squad` is host-level formal invocation wherever it appears; do not include it in a negation and expect a bypass. The formal syntax is:

```text
$agent-academic-squad Plan this cross-module experiment first. Do not execute it. Include expected cost and model assignments.
```

```text
$agent-academic-squad Execute the accepted experiment plan and return the artifacts and validation results.
```

```text
$agent-academic-squad Use Sol max to check this information-theory proof. Report only invalid steps and proposed corrections.
```

You can override defaults at any time:

```text
Do not use Luna for this task; use Sol xhigh for search as well.
```

```text
Do not plan first. Execute directly.
```

## External academic skills

Paper-related subtasks can use separately installed academic skills, including:

- Literature search and deduplication: `nature-academic-search`
- Lawful full-text retrieval: `nature-downloader`
- Full-paper reading: `nature-reader`
- Manuscript writing and polishing: `nature-writing`, `nature-polishing`
- Citation and reference verification: `nature-citation`, `nature-ref-verifier`
- Scientific figures and statistical review: `nature-figure`, `nature-statistics`
- Pre-submission review and reviewer responses: `nature-reviewer`, `nature-response`

These are optional external capabilities and are not bundled in this repository. See [`references/external-skills.md`](references/external-skills.md) for the complete mapping and boundaries.

## Acknowledgements and provenance

The `nature-*` routes in this repository build on the external academic workflows provided by [Nature Skills](https://github.com/Yuan1z0825/nature-skills). Thanks to project founder and maintainer Yuan Yizhe, core developer Ma Xinrui, major contributor Hu Bin, and all [Nature Skills contributors](https://github.com/Yuan1z0825/nature-skills/graphs/contributors) for their open-source work.

Nature Skills is licensed under the [Apache License 2.0](https://github.com/Yuan1z0825/nature-skills/blob/main/LICENSE). This repository provides routing rules for those separately installed skills; it does not include or redistribute their implementations. Refer to the upstream repository for installation, use, and redistribution terms.

## Repository structure

```text
agent-academic-squad/
├── SKILL.md                         # Core workflow
├── LICENSE                          # MIT License
├── README.md                        # English documentation
├── README.zh-CN.md                  # Simplified Chinese documentation
├── .github/workflows/               # Static CI and manual E2E workflow
├── agents/openai.yaml               # Codex UI metadata
├── evals/trigger-routing.csv        # Trigger and routing regression cases
├── evals/e2e-cases.json             # Core schema-v2 E2E expectations
├── evals/nature-integration-cases.json # Optional Nature integration suite
├── evals/receipt-schema.json        # Structured self-report schema
├── evals/fixtures/                  # Real read/write E2E fixture trees
├── references/routing.md            # Model and effort routing
├── references/external-skills.md    # External academic skill mapping
├── scripts/plan_cache.py             # Temporary plan allocation and cleanup
├── scripts/radar_snapshot.py         # Optional read-only Codex Radar snapshot
├── scripts/validate_eval_cases.py    # Deterministic eval-data validation
├── scripts/run_e2e_evals.py          # Isolated Codex JSONL eval runner
└── tests/                            # Cache, eval, and Radar unit tests
```

## License

This project is licensed under the [MIT License](LICENSE). External `nature-*` skills remain subject to their upstream licenses.
