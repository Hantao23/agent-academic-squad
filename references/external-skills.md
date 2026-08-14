# External academic skills

Treat the subagent model as the task owner and the external skill as its workflow and tool guide.

The `nature-*` workflows referenced below are provided by [Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills) under the [Apache License 2.0](https://github.com/Yuan1z0825/nature-skills/blob/main/LICENSE). This file defines squad routing only and does not redistribute their implementations.

## Dispatch rules

- Assign at most one primary external skill to a subtask. Split distinct workflows when their deliverables justify separate stages.
- Name the exact installed skill in the assignment and require the subagent to read its complete `SKILL.md` before acting.
- Follow the external skill's pause conditions and output contract. The user's instructions still take priority.
- Do not invoke skills outside the core list below unless the user explicitly requests one for the current task.
- Do not invoke an external skill when the model can complete a bounded code, experiment, or mathematics task without a specialized workflow.

## Core routes

| Task | Primary skill | Boundary |
| --- | --- | --- |
| Multi-source literature search, deduplication, screening, or reference-file management | `nature-academic-search` | Use for broad source discovery and citation management |
| Retrieve lawful full text or requested supporting information | `nature-downloader` | Use only lawful open-access, publisher-API, or user-authorized institutional routes; respect its SI confirmation gate |
| Full-paper reading, translation, or figure/table-aware interpretation | `nature-reader` | Preserve source grounding and the requested reading depth |
| Build a fixed, source-grounded deep-reading card for one paper | `nature-paper-card` | Use for structured single-paper analysis and research ideas, not bilingual translation or formal peer review |
| Draft or restructure manuscript claims, sections, or argument | `nature-writing` | Use for composition, not merely polishing finished prose |
| Polish, translate, or repair academic English and LaTeX layout | `nature-polishing` | Use when the scientific content is already substantially defined |
| Add or verify claim-level citations | `nature-citation` | Its default source scope is Nature/Science/Cell families; use `nature-academic-search` when broader sources are required |
| Verify bibliographic fields, DOI identity, author order, pages, or reference-list consistency | `nature-ref-verifier` | Use for field-level reference auditing; use `nature-citation` when the question is whether a source supports a manuscript claim |
| Create, revise, or audit manuscript figures | `nature-figure` | Resolve the required Python-or-R choice before execution |
| Audit statistical design, analysis, reporting, or figure statistics | `nature-statistics` | Treat as reporting/review unless raw data and explicit authorization for reanalysis are supplied |
| Prepare data availability, repository, dataset-citation, or FAIR outputs | `nature-data` | Keep data and code availability claims auditable |
| Perform a pre-submission or referee-style manuscript review | `nature-reviewer` | Treat as review only; do not revise unless separately authorized |
| Draft or audit a point-by-point reviewer response | `nature-response` | Preserve correspondence between each comment, change, and evidence |
