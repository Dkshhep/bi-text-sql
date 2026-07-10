# QueryForge 轻量语义层 v1 实施版 Spec

## 目标

为 QueryForge 增加一个轻量语义层，参考 WrenAI context layer 思路，但不实现完整 MDL 编译器。v1 让现有 Text-to-SQL 链路能够使用指标口径、字段含义、业务规则、approved joins 和人工确认 SQL 示例。

核心原则：

- `context/<db_id>/` 文件是语义真相源，可审查、可版本化。
- 向量库只是可重建索引。
- 语义层同时服务检索、Prompt 注入和轻量 SQL 语义校验。
- 默认关闭，关闭后现有 CSpider/RAG/Text-to-SQL 链路行为不变。
- v1 验收不依赖 Northwind / AdventureWorksDW；这些业务库作为后续 demo-data 扩展。

## 文件式语义层

新增目录结构：

```text
context/
  <db_id>/
    models.yaml
    metrics.yaml
    relationships.yaml
    rules.md
    sql/
      *.md
```

文件职责：

- `models.yaml`：业务模型、表说明、字段说明、字段别名、隐藏字段、敏感字段。
- `metrics.yaml`：指标口径，例如歌手数量、销售额、订单数、复购率。
- `relationships.yaml`：approved join path。
- `rules.md`：业务规则，分为 `global` 和 `contextual`。
- `sql/*.md`：人工确认过的 NL→SQL 示例。

v1 提供 `context/concert_singer/` 样例。该样例用于验证语义层机制，不宣称具备真实企业 BI 语义深度。

## 数据库变更

新增迁移 `0006_semantic_context_layer`。

新增表：

```text
semantic_doc
- id
- db_id
- doc_type        metric | model | column | relationship | rule | global_rule | example
- name
- content         用于 embedding / keyword 检索的自然语言文本
- payload         原始结构化 JSON
- embedding
- tsv
- created_at
```

同时给 `fewshot_example` 增加：

```text
metadata JSONB DEFAULT '{}'
```

用于标记：

```text
source = cspider | manual | learned
context_db_id = <db_id>
```

## Context 编译器

新增命令：

```bash
python -m eval.ingest_context --db-id concert_singer --replace
make ingest-context DB_ID=concert_singer
```

编译流程：

```text
context/<db_id>/*
→ 解析 YAML / Markdown
→ 生成 semantic_doc rows
→ 生成 confirmed fewshot rows
→ 写入 pgvector
```

`--replace` 行为：

- 删除该 `db_id` 下 `semantic_doc` 派生内容。
- 删除 `fewshot_example.metadata.source in ('manual', 'learned')` 且匹配 `db_id` 的样例。
- 不删除 CSpider 原始 schema / fewshot 数据。

## LangGraph 链路接入

新增节点：

```text
retrieve_semantics
validate_semantics
```

链路变更：

```text
detect_language
→ rewrite
→ expand
→ retrieve_semantics
→ retrieve
→ schema_linking
→ generate_sql
→ validate_sql
→ validate_semantics
→ execute_sql
→ format_answer
```

`retrieve_semantics` 写入 `GraphState`：

```python
semantic_context: str
approved_relationships: str
global_rules: list[str]
matched_metrics: list[dict]
matched_rules: list[dict]
matched_relationships: list[dict]
matched_examples: list[dict]
matched_columns: list[dict]
matched_models: list[dict]
```

检索规则：

- global rules 不走 top-k，按 `db_id` 全量注入。
- metrics / contextual rules / examples / model / column 走 `semantic_doc` 混合检索。
- relationships 按 `db_id` 精确加载，用于 prompt 和语义校验。
- columns 按 `db_id` 精确加载，用于 hidden/sensitive 校验。

## Prompt 改造

`GENERATE_SQL_PROMPT` 增加三段：

```text
# 全局业务规则
{global_rules}

# 命中的业务语义
{semantic_context}

# 审批连接路径
{approved_relationships}
```

生成 SQL 时优先级：

1. SQL 安全规则最高。
2. schema 中不存在的表列禁止使用。
3. 命中的 metric expression / default filters 优先于模型自由推断。
4. approved joins 优先于自行猜 join。
5. similar examples 只作写法参考，不可照抄无关表列。

## 语义校验

新增配置：

```text
CONTEXT_LAYER_ENABLED=false
CONTEXT_DIR=context
SQL_SEMANTIC_VALIDATE_ENABLED=false
SQL_SEMANTIC_VALIDATE_MODE=warn   # warn | enforce
```

v1 校验项：

- SQL 是否使用 hidden columns。
- SQL 是否访问 sensitive columns。
- SQL join 的表对是否存在于 approved relationships。
- 命中 metric 时，SQL 是否包含对应 default filters。

违规处理：

- `warn`：记录 warning，继续执行。
- `enforce`：写入 `error`，进入现有 self-correct 环路。

## 验收

纯逻辑测试：

- 解析 `models.yaml`、`metrics.yaml`、`relationships.yaml`、`rules.md`。
- global/contextual rules 正确分流。
- hidden/sensitive columns 正确进入 payload。
- metric 被编译成可检索 `semantic_doc.content`。
- confirmed SQL markdown 正确解析成 question/sql/metadata。
- `validate_semantics` 能识别 hidden column、未审批 join、缺失 default filter。

轻量集成验证：

- `CONTEXT_LAYER_ENABLED=false` 时现有行为不变。
- `ingest_context --replace` 对同一 db 可重复执行。
- 使用 `context/concert_singer` 验证 `semantic_doc` 写入、global rules 注入、approved joins 出现在 prompt。
- `retrieve_semantics` 对样例问题能召回对应 metric/rule/example。

## 非目标

- v1 不实现完整 WrenAI MDL→SQL 编译器。
- v1 不做 UI 编辑器。
- v1 不自动学习写回 confirmed queries，只支持人工维护 `context/<db_id>/sql/*.md`。
- v1 不假设 Northwind / AdventureWorksDW 无缝接入。
