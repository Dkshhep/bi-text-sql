"""链路各节点的提示词（集中管理，便于后续接 Langfuse Prompt 管理）。"""

from __future__ import annotations

REWRITE_PROMPT = """你是查询改写助手。结合最近的对话历史，把用户最新的问题改写成一个**自包含、明确**的问题，用于数据库检索与 SQL 生成。
- 补全指代（如"它""这些"）与省略的主体。
- 不要回答问题，只输出改写后的问题本身，不加任何解释。

对话历史：
{history}

用户最新问题：{question}

改写后的问题："""

EXPAND_PROMPT = """针对下面的问题，生成 {n} 个语义等价但措辞不同的检索改写问，用于提升召回。
每行一个，不要编号，不要解释。

问题：{question}"""

SCHEMA_TERMS_FILTER_PROMPT = """你是 Text-to-SQL 关键词召回的 schema 词筛选器。请只从给定 tokens 中选择适合作为 schema 关键词召回的词。

筛选规则：
- 只能从 tokens 中选择，不要改写、拆分、合并或发明新词。
- 只保留可能出现在表名、列名、字段含义、枚举值、过滤条件中的词。
- 去除意图词、量词、泛化词、纯操作词、聚合词、排序词。
- 不要因为某个词对 SQL 生成有用就保留；如果它不适合做 schema 关键词召回，应删除。
- “排名、平均、总数、最高、最低、数量”等词默认删除，除非它明确可能对应 schema、字段含义、枚举值或过滤条件。

问题：{question}
tokens：{tokens}

只输出 JSON，格式为：
{{"schema_terms": ["词1", "词2"]}}"""

GENERATE_SQL_PROMPT = """你是资深数据分析师，负责把自然语言问题转成**单条只读 SQL 查询**（{dialect} 方言）。

# 数据库 Schema
{schema}

# 相似示例（参考其写法，不要照抄表名/列名）
{fewshots}

# 业务知识（列含义/指标口径/取值映射，若与 schema 冲突以 schema 为准）
{business}

# 全局业务规则（必须遵守）
{global_rules}

# 命中的业务语义（指标口径/字段说明/上下文规则）
{semantic_context}

# 审批连接路径（优先使用这些 JOIN）
{approved_relationships}

# 规则
- 只生成一条 SELECT 语句，禁止任何写操作（INSERT/UPDATE/DELETE/DDL）。
- 只使用上面 Schema 中出现的表名和列名。
- 命中指标口径时优先使用其 expression、default filters 和 time_column。
- 多表 JOIN 时优先使用审批连接路径，不要自行猜测无依据的 JOIN。
- 需要聚合/分组时正确使用 GROUP BY；需要排序时给出 ORDER BY。
- 直接输出 SQL，不要 markdown 围栏，不要解释。
{correction}

# 问题
{question}

SQL："""

CORRECTION_BLOCK = """
# 上一次尝试失败，请修正
上次 SQL：
{prev_sql}
错误信息：{error}
请生成修正后的 SQL。"""

SUMMARY_PROMPT = """请对下面同一页/小节的若干文档片段做要点总结，输出一段不超过 200 字的中文摘要，
覆盖其中的关键实体、指标与口径，供后续检索定位整页内容使用。只输出摘要本身。

片段：
{content}

摘要："""

ANSWER_PROMPT = """根据下面的查询结果，用「{language}」自然语言简洁回答用户的问题。
- 直接给出结论，必要时列出关键数据。
- 不要编造结果中没有的数据。

用户问题：{question}
执行的 SQL：{sql}
查询结果（列：{columns}）：
{rows}

回答："""
