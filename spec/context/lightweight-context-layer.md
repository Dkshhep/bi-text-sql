# 轻量版 Context Layer：文件式业务语义层

## 背景

当前 QueryForge 实打实做的只有 WrenAI 五层上下文中的 **Structural 层**（`schema_doc` 灌裸 schema）+ 一个 SQL 安全闸门（`app/sql/guard.py`）。语义、业务、学习三层的代码路径存在但默认关闭或无数据来源：

- `DOC_CONTEXT_ENABLED` 默认 `false`（`app/core/config.py`），`rag_chunk` 无默认灌库入口，业务上下文块恒为「（无）」。
- `enriched` / `descriptions` 默认关（`make ingest` 走 `basic`），`app/core/rag/schema_corpus.py` 的表说明分支不进，`eval/generate_schema_descriptions.py` 是未接入主流程的旁路脚本。
- `fewshot_example` 仅来自 CSpider `train.json` 静态入库，无学习回流。

WrenAI 的核心做法是：不让 Agent 直接面对原始 schema，先建一个**可审查、可版本化、可检索**的业务语义层，把 canonical table、字段含义、approved joins、可信定义、历史成功查询显式写下来。本 spec 采用其「knowledge/ 是真相源，索引是可重建派生物」的思路，但**不引入 MDL→SQL 编译器**，落地为文件式语义层，编译进现有 pgvector 表。

## 目标

- 定义一套**文件式**业务语义层（YAML + Markdown），作为语义/业务/连接/历史查询的**版本化真相源**，per 业务库一套。
- 写一个幂等的 `ingest-context` 编译器，把文件编译进**现有** `schema_doc` / `rag_chunk` / `fewshot_example` 三张表，**不新增表、不做迁移**。
- 区分**全局规则**（无条件注入）与**上下文规则**（检索式），在 generate_sql 提示中分通道使用。
- 为 **(B) 式校验闸门**（approved joins / 允许列集）预留接口，但 v1 不实现硬保证。

## 非目标

- 不实现 MDL→物理 SQL 的编译器 / `dry-plan`（LLM 仍直接对物理表写 SQL）。
- 不实现 cubes / measures 指标对象、views、层级维度。
- 不新增数据库表，不改 alembic 迁移。
- 不做 UI / 编辑器。
- 不追求提升 CSpider EX/ragas 分数（本特性面向单一业务库的真实部署，与 benchmark 正交）。
- 不宣称拥有"列级访问控制"——v1 的隐藏列/approved join 是**提示级**（除非启用可选校验闸门）。

## 作用机制的定位（关键区分）

WrenAI 的 context 有两种机制，本 spec **v1 只交付 (A)，为 (B) 留接口**：

- **(A) Context 作为检索/提示**：描述、join 提示、规则、示例进 prompt，LLM 仍对物理表写 SQL，建议性、可被无视。
- **(B) Context 作为校验闸门**（QueryForge 特有中间路，非 WrenAI 编译器）：生成后用 sqlglot 解析 SQL，校验所用表/列是否在允许集、join 是否走审批路径，违规打回 `self_correct` 重生成。复用现有 `validate_sql` → `self_correct` 环路。v1 只留接口与配置位，不实现。

## 文件布局

真相源放在版本库中，根目录 `context/<db_id>/`：

```text
context/
  <db_id>/
    models.yaml        # 表的业务包装：描述、字段别名/描述、隐藏列
    relationships.yaml # approved join paths
    rules.md           # 业务规则，分 global / contextual 两节
    sql/               # confirmed NL→SQL pairs，一文件一对
      *.md
```

### models.yaml

```yaml
db_id: concert_singer
models:
  - table: singer
    description: 歌手主表，记录歌手基本信息与所属国家。
    columns:
      - name: Singer_ID
        alias: 歌手ID
      - name: Name
        alias: 姓名
      - name: internal_flag
        hidden: true          # v1：不写入 schema_doc（提示级隐藏）
```

### relationships.yaml

```yaml
db_id: concert_singer
relationships:
  - name: singer_in_concert__singer
    models: [singer_in_concert, singer]
    join_type: MANY_TO_ONE
    condition: singer_in_concert.Singer_ID = singer.Singer_ID
    approved: true
```

### rules.md

```markdown
## global
- 查询默认排除测试歌手：Name NOT LIKE 'TEST_%'

## contextual
- 客户分析优先用 canonical 表 singer，而非历史遗留表。
```

### sql/*.md（confirmed pair）

```markdown
---
db_id: concert_singer
question: 有多少个歌手？
source: manual          # manual | learned（学习回路写回时标 learned）
---
SELECT count(*) FROM singer;
```

## 编译流程（ingest-context）

新增 `python -m eval.ingest_context [--db-id X] [--replace]`，`make ingest-context` 包装。幂等、可重建：

```text
context/<db_id>/*
  ├─ models.yaml        → 合成 descriptions dict + 隐藏列集
  │                       → 复用 build_schema_docs(enriched=True, descriptions=...)
  │                       → 隐藏列从 schema_doc 内容中剔除（提示级隐藏）
  │                       → upsert_schema_docs
  ├─ relationships.yaml → 渲染成 approved-join 文本，作为 db 级 schema_doc 附加段
  │                       → （B 接口）导出 allowed-join 结构供校验闸门读取
  ├─ rules.md[contextual] + models 描述 → upsert 到 rag_chunk（走现有检索）
  ├─ rules.md[global]   → 编译进 context/<db_id>/_global.json（不进检索，主链路直读注入）
  └─ sql/*.md           → upsert_fewshots，metadata 标记来源（source=manual|learned）
```

重建纪律：pgvector 中的 context 内容视为派生物，`--replace` 按 db_id 清理后重灌，保证与文件一致。

### fewshot 来源标记

`fewshot_example` 并存两类来源，用 metadata 区分：

- `source=cspider`：CSpider `train.json` 静态入库（现状，`ingest_cspider.py` 写入时补标记）。
- `source=manual`：`context/<db_id>/sql/*.md` 中人工确认的 pair。
- `source=learned`：学习回路自动写回（下一个 spec），仍先落成 `sql/*.md` 文件再编译。

来源标记用于日后按来源加权、过滤或清理，v1 只负责写入，不改检索排序。

## 主链路改动

改动点最小化，集中在 retrieve / generate_sql / prompts：

1. **全局规则注入**（新通道）：`generate_sql` 读取 `_global.json` 的 global 规则，无条件拼进 prompt 的新 `# 全局规则` 段。不走检索，避免 top-k 漏召回。
2. **上下文规则 + few-shot**：沿用现有 `doc_context` / `fewshots` 检索通道，`DOC_CONTEXT_ENABLED` 在启用 context 层的库上打开。
3. **提示词**（`app/core/langgraph/prompts.py`）：`GENERATE_SQL_PROMPT` 增加 `# 全局规则`（强制）与 `# 审批连接路径`（来自 relationships）两段；保留现有 `# 业务知识` 作上下文规则。
4. **(B) 校验闸门接口（可选，默认关）**：新增 `SQL_ENFORCE_ALLOWED_SET`（默认 `false`）。开启时 `validate_sql` 额外校验 SQL 引用的表/列 ∈ 允许集、join ∈ approved paths，违规写 `error` 走 self_correct。v1 只留接口与配置位，实现后续补。

## 配置

```text
CONTEXT_LAYER_ENABLED=false        # 总开关；关时行为与现状完全一致
CONTEXT_DIR=context                # 文件式语义层根目录
SQL_ENFORCE_ALLOWED_SET=false      # (B) 校验闸门，v1 默认关
```

`CONTEXT_LAYER_ENABLED=false` 时全链路退化为现状，零行为变化。

## 与现有机制的关系

- 与 `spec/retrieval/keyword-recall-evolution.md` 正交：本 spec 只改语料内容与 prompt，不动关键词/向量召回逻辑。
- 与学习回路（后续 spec）衔接：`sql/*.md` 即 confirmed pairs 的真相源；未来"成功查询自动写回"应写成 `source=learned` 的 `sql/*.md` 文件（保持可审查），再 `ingest-context` 重建，而非直接写库。
- 与 `eval/generate_schema_descriptions.py` 衔接：该脚本作为 scaffold，产出 `models.yaml` 的 `description` 草稿，人工 enrich 后入版本库（scaffold fast, enrich deep）。

## 落地范围（v1）

**做**：文件格式 + `ingest-context` 编译器 + 全局规则注入 + approved-join 提示段 + fewshot 来源标记 + (B) 接口与配置位。
**不做**：MDL→SQL 编译器、cubes、UI、成功查询自动写回（属下一个 spec）、(B) 闸门的完整实现。

## 验收

- `CONTEXT_LAYER_ENABLED=false`：现有 `make test` 全绿，主链路无行为变化。
- 提供一个 CSpider 库（如 `concert_singer`）的 `context/` 样例，`make ingest-context --db-id concert_singer --replace` 后：
  - `schema_doc` 含表说明与字段别名（enriched），隐藏列不出现在内容中；
  - global 规则出现在 generate_sql 的完整 prompt（DEBUG 日志可验证）；
  - approved joins 出现在 prompt 的连接路径段；
  - `sql/*.md` 的 pair 能被 few-shot 检索命中，且 metadata 标记 `source=manual`。
- 新增纯逻辑单测：文件解析、隐藏列剔除、global/contextual 分流，不依赖 DB/LLM（符合 `tests/` 约定）。
