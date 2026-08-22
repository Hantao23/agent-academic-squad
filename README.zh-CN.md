# agent 学术小分队

[English](README.md) | **简体中文**

一个面向 Codex 的轻量、学术优先任务调度 Skill，也支持用户显式交办其他任务。

它只对明确的学术任务开放隐式触发，并继续判断调度能否带来实质收益；用户也可以用正式 `$agent-academic-squad` 或正向“`小分队...`”显式交办非学术任务。读取一个文件、网页或调用一次工具本身不代表需要调度；规划、协调、广泛材料处理、专业 Skill 组合或独立审查确有帮助时，小分队才增加相应处理。

## 它解决什么问题

学术工作通常落在三类领域：

- 代码与实验：任务规划、实现、调试、实验设计与执行；
- 数学与算法：公式检查、策略分析、算法构造和形式化证明；
- 论文工作：文献检索、全文阅读、写作、润色、引用、审稿和回复。

这些任务需要的模型、推理强度和上下文并不相同。本 Skill 将“规划”和“执行/审查”分开，并同时判断：

- **工作量成本**：任务会花多少时间、计算和上下文；
- **错误决策代价**：错误结论会不会影响科学主张、实验重跑或重要产物。

高成本任务默认先规划并停下，等待用户决定是否执行；边界清楚的任务可以直接交给合适的执行者。

## 工作方式

```mermaid
flowchart TD
    A["用户提出任务"] --> B["主模型做轻量分诊"]
    B --> C["识别阶段：规划 / 执行 / 审查"]
    B --> D["识别领域：代码实验 / 数学算法 / 论文 / 显式通用任务"]
    C --> E["分别判断工作量与错误代价"]
    D --> E
    E --> F{"任务是否适合直接处理？"}
    F -- "是" --> G["主模型回答或委派一个执行者"]
    F -- "高成本且尚无计划" --> H["委派规划者并返回计划"]
    H --> I["用户决定是否执行"]
    I --> G
    G --> J["返回结果、证据和产物供用户验收"]
```

核心原则：

- 使用与任务相称、足够且合适的调度、结构、上下文和输出；不以轻量为理由牺牲质量或完整性，也不在没有收益时增加复杂度；
- 学术领域只约束隐式触发；普通软件或产品开发、无科研背景的日常代码、商业运营、一般写作、个人事务和常识问答不会隐式触发，但用户可以用 `$agent-academic-squad` 或正向“`小分队...`”显式交办；
- 不能只因任务出现“代码、数学、分析、写作、规划或审查”等词就认定为学术任务；学术背景不明确时保持不触发；
- 允许隐式触发；当前会话的 `GPT-5.6 Sol medium` 足以承担轻量分诊，不要求先把主模型切到 xhigh；
- 单个文件、摘要、短脚本、小表格、段落润色或一次工具调用本身不足以触发；只有调度确实能改善可靠性时才启用；
- 用户指定的模型和推理强度永远优先于默认路由；
- 每次小分队完成回答都会说明实际调用了哪些子代理模型、推理强度及任务；没有调用时明确说明“本次未调用子代理”，不报告主模型；
- 默认只派一个子代理，只有真正独立的工作才并行；
- 多阶段任务只识别真正影响结果的依赖，子代理按可独立验证的证据或产物边界拆分，冲突依据证据处理而不是投票；
- 主模型先判断哪些对话内容需要保留，再选择性继承最近对话或摘录关键信息，并补充中立、可核验的文件与证据索引；
- 学术小分队判定计划、审查报告或交接说明具有后续复用价值时，会自动保存由调度器生成的辅助 Markdown，但文件和聊天都不套用统一模板；
- 管理型缓存只拥有小分队新生成的辅助文本；项目文件和外部 Skill 产物留在原获授权位置，辅助文件只引用路径而不复制；
- 当多个当前可回答的用户决策确实阻塞任务时，小分队可以调用一次 `grilling`，把第一层 frontier 连同建议批量返回，然后停止等待；单个阻塞直接询问；
- 规划请求只返回计划，不在同一轮偷偷执行；
- 审查任务默认只报告问题，不擅自修改产物；
- 小任务由主模型直接回答，不为“使用多代理”而使用多代理。

完整规则见 [`SKILL.md`](SKILL.md)，模型选择见 [`references/routing.md`](references/routing.md)。

## 项目产物与辅助产物缓存

任务执行可能产生源代码、数据或实验输出、日志、模型权重、图表、论文、PPT、保存为项目交付物的报告或审查结果，以及外部 Skill 的输出。这些都是项目产物：它们归项目所有，保留在用户授权的项目位置，并从原位置返回或引用。

小分队的自动缓存用途要窄得多：它只能保存调度器为了回传或续接任务而生成、具有复用价值的计划、审查报告和交接说明。如果用户把其中一项指定为项目交付物或给出了项目内保存位置，它仍归项目所有。缓存不会重复复制项目产物，也不会引入固定模板。

当辅助产物对后续执行、逐项核查或可靠续接具有明显价值，并且不再只是一次临时短答时，小分队就自动保存。它不必长到聊天容纳不下，也不设置固定字数、章节数或问题数量门槛；短计划、简单审查和普通回答仍只在聊天中返回。边界接近时，只要不涉及敏感信息或项目产物归属，优先使用会自动过期的临时缓存。无论 Skill 是显式调用还是隐式触发，规则相同，用户也可以明确说“不要保存”关闭本次写入。

辅助产物自动保存分为临时缓存和持久存储：

- 未明确要求永久保存时，辅助文件进入管理型缓存，默认保留 30 天；
- 明确要求永久保存或指定路径时，文件持久保存；
- 临时文件可在过期前复制到持久路径；
- 主模型说明绝对路径、保存状态、保留期限和真实任务状态；保存计划仍不代表开始执行。

临时缓存默认位于项目内，并按类别和 UTC 月份组织：

```text
<workspace-root>/.tmp/agent-academic-squad/{plans,reviews,handoffs}/<YYYY-MM>/<DDTHHMMSSZ>-<task-slug>.md
```

当最终答复只存在于对话或工具输出中时，调度器通过标准输入把原始字节直接交给 `persist_final.py`，不得仅为了生成受管副本就在工作区创建固定名称的 `*-source.md`、`*_final.md`、哈希快照或其他中转文件。独立存在的源文件可以原地读取，但仍归调用方所有。真正的一次性计算中间物应放入自动清理的系统临时目录或用户另行授权的实验位置；完成前，调度器要确认自己没有在受管布局之外遗留中转文件。

`scripts/artifact_cache.py` 只创建本次所需的类别目录和当月目录，每次新建文件而不追加或覆盖旧产物，并执行惰性清理。它只进入合法月份目录，只删除符合自身命名规则且超过 30 天的普通文件，随后移除已经为空的受管月份目录；它不跟随符号链接，也不删除项目缓存根目录之外的内容。项目位于 Git 工作树时，只有 `.tmp/agent-academic-squad/` 已被忽略才自动保存，Skill 不会自行修改忽略规则。如果该检查或其他安全检查阻止保存，主模型会在聊天中保留完整结果，并用一句话说明未保存的具体原因。用户未指定路径的持久文件按类别保存到当前工作区的 `.agents/plans/`、`.agents/reviews/` 或 `.agents/handoffs/`。

自动保存不会写入原始凭据、访问令牌、私钥，也不会默认复制完整对话。它也不得为了交接而复制、移动、重命名、改写或缓存项目产物。辅助文件只使用这些产物在原获授权路径中的位置和必要证据索引；归属不明确时保持原位。用户明确要求复制、转换、移动或另存到获授权位置时，仍以用户指令为准。用户标记为敏感、机密或“不要存储”的材料只在聊天中返回；除非用户另行给出获授权的保存位置。

辅助文件没有强制章节或固定顺序。计划保留重要分支和执行细节，审查报告保留关键发现及证据，交接说明保留可靠续接所需的上下文；不适用的内容直接省略，不为满足格式填写空栏目。

辅助文件用于补充聊天，而不是迫使两边重复。聊天仍按任务复杂度说明主线或发现、真正需要用户决定的事项、重要限制、当前状态和文件绝对路径；详细内容可以留在文件中，重复它们只会浪费 token 时无需再贴一遍。

## 默认模型路由

默认值是建议，不是限制：

| 场景 | 默认方向 |
| --- | --- |
| 简单规划或范围明确的局部代码 | Sol medium |
| 中等复杂度规划或边界清楚的非简单代码，包括常规多文件修改 | Sol high |
| 复杂规划、耦合的跨模块代码、困难诊断或重要审查 | Sol xhigh |
| 关键算法或重大架构决策 | Sol max |
| 固定且可测试的实验协议执行 | Luna max |
| 数学策略与算法构造 | Sol xhigh |
| 形式化证明或困难推导 | Sol max |
| 大范围文献检索与初筛 | Luna max |
| 全文阅读与长材料证据提取 | Terra max |
| 论文核心写作、重构或投稿级审查 | Sol xhigh |

模型 ID、升级条件与 Codex Radar 规则以 [`references/routing.md`](references/routing.md) 为准。若用户明确指定模型，Skill 不会静默替换。

## 安装

当前官方 Codex 文档推荐用户级 Skill 放在 `$HOME/.agents/skills`，仓库级 Skill 放在项目的 `.agents/skills`：

```bash
git clone https://github.com/Hantao23/agent-academic-squad.git "$HOME/.agents/skills/agent-academic-squad"
```

```bash
git clone https://github.com/Hantao23/agent-academic-squad.git .agents/skills/agent-academic-squad
```

部分 Codex Desktop 或旧版 Codex 环境可能仍从 `$CODEX_HOME/skills`（通常为 `~/.codex/skills`）发现用户 Skill：

```bash
git clone https://github.com/Hantao23/agent-academic-squad.git "${CODEX_HOME:-$HOME/.codex}/skills/agent-academic-squad"
```

随后重启 Codex，或开启一个新任务让 Skill 清单重新加载。

该 Skill 依赖支持子代理调度的 Codex 环境。`scripts/radar_snapshot.py` 只使用 Python 3 标准库；只有在模型选择确实可能受当前数据影响时才会访问公开的 Codex Radar 数据源。

## Evals

评测覆盖正式与自然语言触发、隐式触发、上下文二次识别和负例边界、阶段/领域路由、模型与推理强度选择、规划与执行的区分、超大任务事前判断与中途扩容分阶段、写入和产物边界、single-writer、单轮两个子代理上限、用户覆盖、长时任务交接及隔离审查。核心数据集包含58条路由案例和20条 E2E 案例；独立可选 manifest 包含两条 Nature 集成案例和一条 `grilling` 集成案例，因此核心评测不依赖这些外部 Skill。

运行以下确定性检查：

```bash
python3 scripts/validate_eval_cases.py
python3 -m unittest discover -s tests -v
python3 scripts/run_e2e_evals.py --dry-run --max-cases 3
python3 scripts/run_e2e_evals.py --manifest evals/nature-integration-cases.json --dry-run
python3 scripts/run_e2e_evals.py --manifest evals/grilling-integration-cases.json --dry-run
```

这些命令校验数据集、单元行为和 runner manifest；dry-run 不调用模型。Codex CLI 可使用有效的 `CODEX_API_KEY` 时，可选的真实 E2E 烟雾评测为：

```bash
python3 scripts/run_e2e_evals.py --strict-isolation --strict \
  --case e2e-direct-bounded-academic \
  --case e2e-implicit-plan \
  --case e2e-four-directory-read-only-review
```

真实 E2E 会调用模型并可能消耗 API 配额；每条案例在隔离的临时工作区运行，结果写入 `evals/results/`。认证、网络和超时失败与 Skill 行为分开报告；缺少必需证据时结果为 `inconclusive`。只有已安装相应外部 Skill 时才使用可选 manifest，并通过 `--external-skill-root` 指向安装根目录。

## 使用示例

作为尽力匹配的自然语言快捷触发，可以让消息以“`小分队`”开头；冒号、逗号和空格均可省略。这个快捷词仍依赖 Codex 根据 description 匹配到本 Skill；`$agent-academic-squad` 才是正式显式调用语法。

```text
小分队帮我审查这三个实验目录，按测序深度输出表格。
```

```text
这个交给小分队，只规划，不执行。
```

`不用小分队`、`不要交给小分队` 等自然语言否定，以及仅仅讨论“小分队”的句子，不会触发快捷词。学术范围只限制隐式触发；`$agent-academic-squad` 或正向“`小分队...`”会显式启用这套调度，也可以用于非学术任务。引号或代码里的字面提及不算交办。显式启用不会绕过安全、授权或用户的真实指令，也不代表简单任务必须派子代理。正式用法例如：

```text
$agent-academic-squad 先规划这个跨模块实验，不要执行，给出预计成本和模型分配。
```

```text
$agent-academic-squad 直接执行已经确认的实验计划，完成后把产物和验证结果返回给我。
```

```text
$agent-academic-squad 用 Sol max 检查这个信息论证明，只报告不成立的步骤和修正建议。
```

```text
$agent-academic-squad 审查这份复杂的跨团队产品迁移方案，找出依赖和回滚缺口，不要修改。
```

```text
$agent-academic-squad 找一个子代理精读这篇论文，再由另一个执行者据此重写方法部分。
```

你随时可以覆盖默认选择：

```text
这次不要 Luna，检索也用 Sol xhigh。
```

```text
不要先规划，直接执行。
```

## 外部 Skills

对于涉及哈希、缓存键、manifest、resume gate、失效逻辑或 mismatch 触发重跑的代码与实验任务，小分队可以使用独立安装的 [`hash-boundary`](https://github.com/Hantao23/hash-boundary) Skill。范围较小的任务由调度器直接应用；以哈希设计、审查或实现为核心的委派任务，则由同一个任务负责人使用该 Skill，不会仅仅因为出现哈希就额外增加一个子代理。任何重算、删除、拒绝续跑或任务扩张，都必须先把 mismatch 追溯到确实会改变受保护结果的语义生产输入。

将它作为用户级 Skill 安装在小分队旁边：

```bash
git clone https://github.com/Hantao23/hash-boundary.git "$HOME/.agents/skills/hash-boundary"
```

当多个相互关联、必须由用户决定且当前可以同时回答的阻塞项出现时，小分队可以调用一次独立安装的 `grilling`。它把当前 frontier 连同建议一次性批量返回后停止；单个简单问题、可自行调查的事实或自动多轮追问不会触发它。

论文类子任务可以继续调用专门的外部 Skill，例如：

- 文献检索与去重：`nature-academic-search`
- 合法全文获取：`nature-downloader`
- 全文阅读：`nature-reader`
- 论文写作与润色：`nature-writing`、`nature-polishing`
- 引用与参考文献核验：`nature-citation`、`nature-ref-verifier`
- 科研绘图与统计审查：`nature-figure`、`nature-statistics`
- 投稿前审稿与审稿回复：`nature-reviewer`、`nature-response`

这些是独立安装的可选能力，不包含在本仓库中。完整映射和边界见 [`references/external-skills.md`](references/external-skills.md)。

## 致谢与来源

本仓库中的 `nature-*` 路由建立在 [Nature Skills](https://github.com/Yuan1z0825/nature-skills) 提供的外部学术工作流之上。感谢项目创始人及维护者袁一哲、核心开发者马昕瑞、主要贡献者胡彬，以及所有 [Nature Skills contributors](https://github.com/Yuan1z0825/nature-skills/graphs/contributors) 的开源工作。

Nature Skills 采用 [Apache License 2.0](https://github.com/Yuan1z0825/nature-skills/blob/main/LICENSE)。本仓库仅提供面向这些外部 Skills 的任务调度和路由规则，不包含或重新发布其实现；安装、使用与再分发相关能力时，请以 Nature Skills 上游仓库为准。

一轮式阻塞澄清路线建立在 Matt Pocock Skills 仓库提供的外部 [`grilling` Skill](https://github.com/mattpocock/skills/tree/main/skills/productivity/grilling) 之上。其当前上游工作流支持在每轮批量询问整个已解锁 frontier，并采用 [MIT License](https://github.com/mattpocock/skills/blob/main/LICENSE)。本仓库只提供路由和“一轮后停止”的约束，不重新发布其实现。

## 仓库结构

```text
agent-academic-squad/
├── SKILL.md                         # 主工作流
├── LICENSE                          # MIT License
├── README.md                        # 英文文档
├── README.zh-CN.md                  # 简体中文文档
├── .github/workflows/               # 静态 CI 与手动 E2E 工作流
├── agents/openai.yaml               # Codex 界面元数据
├── evals/trigger-routing.csv         # 触发与路由回归案例
├── evals/e2e-cases.json              # 核心 E2E 预期
├── evals/nature-integration-cases.json # 可选 Nature 集成集
├── evals/grilling-integration-cases.json # 可选一轮式 grilling 集成集
├── evals/receipt-schema.json         # 结构化自述 schema
├── evals/fixtures/                   # 真实读写 E2E fixture
├── references/routing.md            # 模型与推理强度路由
├── references/external-skills.md    # 外部 Skill 映射
├── scripts/artifact_cache.py         # 管理型辅助产物路径与安全清理
├── scripts/radar_snapshot.py         # 可选的 Codex Radar 只读快照
├── scripts/validate_eval_cases.py    # Eval 数据确定性校验
├── scripts/run_e2e_evals.py          # 隔离的 Codex JSONL Eval runner
└── tests/                            # 缓存、评测和 Radar 单元测试
```

## License

本项目采用 [MIT License](LICENSE)。外部 `nature-*` Skills 仍适用各自上游许可证。
