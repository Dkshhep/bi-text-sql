# 关键词召回演进：后端分词 + LLM 筛词兜底召回

## 背景

当前关键词检索使用 PostgreSQL 全文检索：

```sql
tsv @@ plainto_tsquery('jiebacfg', query)
```

`plainto_tsquery` 会把自然语言问题中的分词结果按 AND 语义组合。中文 Text-to-SQL 问题中经常包含“查询、显示、前、名、信息”等不会出现在 schema 中的词，导致关键词检索通道即使存在相关表名或列名，也可能因为部分无关词未命中而返回空结果。

例如：

```text
查询成绩排名前5名的学生信息
```

原逻辑可能要求“查询、成绩排名、前、名、学生、信息”等词全部命中，导致只包含“学生、成绩”的 schema 文档无法通过关键词检索召回。

## 目标

将关键词通道从“自然语言全文匹配”演进为“backend-tokenized schema-aware sparse retrieval”：

- 保留现有关键词检索作为第一阶段。
- 只有当原关键词逻辑返回空结果时，才进入新的兜底召回。
- 兜底召回先使用当前关键词后端分词，再由 LLM 从分词 tokens 中筛选 schema terms。
- 使用筛选后的 schema terms 做 OR 召回，并通过百分比命中阈值控制噪声。
- 默认仅对 `schema_doc` 启用，`fewshot_example` 与 `rag_chunk` 默认关闭，但三类语料都必须支持配置开关。

## 非目标

- 不替换向量召回。
- 不改变原问题。
- 不改变 SQL 生成输入。
- 不移除现有关键词逻辑。
- 不让 LLM 自由生成 schema terms；LLM 只能从后端分词 tokens 中筛选。

## 数据流

```text
question / rewritten_question
  -> 原关键词检索
  -> 原检索为空时进入兜底
  -> 当前关键词后端分词
  -> LLM 从 tokens 中筛选 schema_terms
  -> schema_terms OR 召回
  -> 百分比命中阈值过滤
  -> RRF 融合
  -> rerank
```

召回顺序固定为：

1. 使用现有 `keyword_search(table, query, top_k, db_id)` 逻辑。
2. 若原逻辑有结果，直接返回，不触发新逻辑。
3. 若原逻辑无结果，且对应语料表开关启用，则触发 schema terms 兜底召回。
4. 若分词、LLM 筛选或兜底召回失败，返回原关键词逻辑的空结果，由向量召回继续兜底。

## 配置

新增表级配置开关：

```python
KEYWORD_SCHEMA_TERMS_SCHEMA_DOC_ENABLED = True
KEYWORD_SCHEMA_TERMS_FEWSHOT_ENABLED = False
KEYWORD_SCHEMA_TERMS_RAG_CHUNK_ENABLED = False
```

新增阈值配置：

```python
KEYWORD_SCHEMA_TERMS_MIN_MATCH_RATIO: float
```

`KEYWORD_SCHEMA_TERMS_MIN_MATCH_RATIO` 不在本规格中写死默认值，但必须支持环境变量配置。

阈值计算：

```python
min_match = max(1, ceil(len(schema_terms) * ratio))
```

该规则保证只有一个 schema term 时，至少命中 1 个即可召回；多个 schema terms 时按比例计算命中门槛。

## 后端分词

schema terms 生成必须先使用当前关键词后端分词，保证筛选后的词与后续 matching 语义一致。

### pg_jieba

当 `RETRIEVAL_BACKEND=pg_jieba` 时，使用 PostgreSQL / pg_jieba 分词能力生成 tokens，确保 tokens 与 `tsv`、`tsquery` 语义一致。

### Elasticsearch

当 `RETRIEVAL_BACKEND=es` 时，使用 Elasticsearch analyzer 生成 tokens，确保 tokens 与 ES index matching 语义一致。

## LLM 筛词

LLM 只做“从后端 tokens 中筛选”，不从原问题自由抽词。

LLM 输入包含：

- 原问题或改写后问题。
- 当前关键词后端产生的 tokens。
- 筛选规则。

LLM 输出固定为 JSON：

```json
{"schema_terms": ["学生", "成绩"]}
```

实施时必须对 LLM 输出做后处理：

- 丢弃不在后端 tokens 中的词。
- 去重并保持原 tokens 顺序。
- 丢弃空字符串、特殊字符、明显非法 tsquery / ES query 片段。
- JSON 非法或 `schema_terms` 为空时跳过兜底逻辑。

### Prompt 约束

LLM 必须遵守：

- 只能从给定 tokens 中选择，不自行发明新词。
- 只保留可能出现在表名、列名、字段含义、枚举值、过滤条件中的词。
- 去除意图词、量词、泛化词、纯操作词、聚合词、排序词。
- 不保留仅对 SQL 生成有用、但不适合做 schema 关键词召回的概念词。

应去除的词包括但不限于：

```text
查询、显示、列出、信息、前、名、个、所有、哪些
```

以下操作、聚合、排序概念词默认不保留，除非它明确可能对应 schema、字段含义、枚举值或过滤条件：

```text
排名、平均、总数、最高、最低、数量
```

例如：

```text
问题：查询成绩排名前5名的学生信息
后端 tokens：["查询", "成绩", "排名", "前", "名", "学生", "信息"]
schema_terms：["成绩", "学生"]
```

## 兜底召回

使用筛选后的 schema terms 构造 OR 查询。

### pg_jieba 召回

pg_jieba 后端使用 PostgreSQL 全文检索 OR 查询。候选的 `_kscore` 使用 schema terms OR 查询计算，语义对应 PostgreSQL `ts_rank_cd` 的关键词相关性分数。

### ES 召回

ES 后端使用 `bool.should` + `minimum_should_match`。候选的 `_kscore` 使用 ES `_score` 归一后的关键词分数。

### 候选放大与过滤

兜底召回先取 `top_k * N` 个候选，再按 `min_match` 过滤，最后返回 `top_k`。`N` 应实现为配置或内部常量，避免 OR 查询候选过少导致阈值过滤后无结果。

## 排序规则

兜底召回排序规则固定为：

```text
matched_terms DESC,
_kscore DESC,
id ASC
```

含义：

- `matched_terms`：候选命中的 schema terms 数量，优先保证候选覆盖更多 schema 关键词。
- `_kscore`：关键词后端基于 schema terms OR 查询计算出的相关性分数；pg_jieba 下对应 `ts_rank_cd`，ES 下对应 ES `_score` 归一后的关键词分数。
- `id ASC`：稳定排序，避免同分结果顺序漂移，方便测试和排查。

示例：

```text
schema_terms = ["学生", "成绩", "班级"]
min_match = 2

doc1: matched_terms=3, _kscore=0.05
doc2: matched_terms=2, _kscore=0.18
doc3: matched_terms=2, _kscore=0.12
doc4: matched_terms=1, _kscore=0.30
```

过滤后 `doc4` 被丢弃，排序结果为：

```text
doc1, doc2, doc3
```

`doc1` 虽然 `_kscore` 低于 `doc2`，但命中更多 schema terms，因此排在前面。

## 状态与接口

新增图状态字段：

```python
schema_terms: list[str]
```

`schema_terms` 由兜底召回前的筛词流程产出，只服务关键词召回。该能力独立于 `QUERY_EXPANSION_ENABLED`，不影响 `expanded_queries`。

## 降级策略

以下情况必须跳过新兜底逻辑：

- 后端分词失败。
- LLM 调用失败。
- LLM 返回非 JSON。
- LLM 输出为空。
- LLM 输出 terms 全部不在后端 tokens 中。
- 表级开关关闭。

跳过后返回原关键词逻辑的空结果，由向量召回继续兜底。不因 schema terms 生成失败阻断主链路。

## 观测与日志

日志应记录：

- 原关键词召回数量。
- 后端分词 tokens。
- LLM 筛选后的 schema terms。
- 兜底是否触发。
- 表级开关状态。
- 兜底候选数。
- 阈值过滤后数量。
- `min_match` 与 `ratio`。

## 风险

- 后端分词粒度不理想时，LLM 只能在已有 tokens 中筛选，无法补出缺失词。
- OR 召回过宽可能带来候选噪声。
- 过滤掉排序/聚合词后，关键词召回更专注 schema，但可能失去少量业务文档中的概念匹配。
- pg_jieba / ES analyzer 的 token 输出不同，导致不同后端下召回表现不同。

## 验收标准

- 原关键词有结果时，新逻辑不触发。
- `schema_doc` 原关键词无结果时，默认触发后端分词 + LLM 筛词兜底。
- `fewshot_example` 和 `rag_chunk` 原关键词无结果时，默认不触发兜底。
- 开关启用后，对应语料表可触发兜底。
- LLM 不得输出 tokens 之外的词；若输出，实施时必须过滤掉。
- LLM 不保留仅对 SQL 生成有用的操作/聚合/排序概念词，除非它明确可能对应 schema 或过滤值。
- 单个 schema term 时阈值为 1。
- 多个 schema terms 时按比例计算阈值。
- 分词或 LLM 失败不影响主链路。

## 测试计划

- 单测表级默认配置：`schema_doc=true`，`fewshot_example=false`，`rag_chunk=false`。
- 单测后端 tokens 过滤：LLM 输出不在 tokens 中的词会被丢弃。
- 单测 LLM 筛词规则：`查询/显示/列出/信息/前/名/个/所有/哪些` 被过滤。
- 单测 LLM 筛词规则：`排名/平均/总数/最高/最低/数量` 默认被过滤，除非作为明确 schema/过滤值出现在 tokens 场景中。
- 单测 schema terms JSON 解析：合法 JSON、非法 JSON、空数组、重复词、特殊字符。
- 单测阈值计算：1、2、3、5 个 terms 在不同 ratio 下的 `min_match`。
- 单测召回分支：
  - 原关键词返回非空时不调用分词和 LLM。
  - `schema_doc` 原关键词返回空时默认调用兜底。
  - `fewshot_example`、`rag_chunk` 原关键词返回空时默认不调用兜底。
  - 显式开启表级开关后，对应表原关键词为空时调用兜底。
- 单测排序：按 `matched_terms DESC, _kscore DESC, id ASC` 排序。
- 集成测试用例：
  - “查询成绩排名前5名的学生信息” 经后端分词后，LLM 筛掉“查询/排名/前/名/信息”，保留 schema 相关词如“成绩/学生”。
  - 只有一个 schema term 的问题可以正常召回。
  - 分词失败或 LLM 筛词失败时链路不中断。

