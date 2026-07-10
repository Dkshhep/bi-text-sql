# Schema 分层存储与两阶段召回 Spec

状态：Draft v0.3（待进一步评审，禁止据此直接实施）

## 1. 背景

当前 `schema_doc` 采用“一张表一条记录”的方式：

- `doc_type=db`：数据库物理概要；
- `doc_type=table`：表名、字段、字段类型、主键和外键。

该设计适用于字段较少的表，但宽表可能包含数百个字段，会产生以下问题：

- 单条 embedding 文本过长，字段之间互相稀释；
- 用户查询边缘字段时，整表文档可能无法有效召回；
- 多张宽表同时召回时，`linked_schema` 体积过大；
- Schema 检索结果难以进行字段级裁剪。

项目同时存在 `semantic_doc`，用于保存表、字段、指标、关系和规则的业务语义。本方案明确区分物理结构与业务语义，并为宽表引入分块存储和两阶段召回。

## 2. 已确定的设计原则

### 2.1 `schema_doc` 只保存物理结构

`schema_doc` 可以保存：

- 数据库和表的物理名称；
- 字段名称、类型和顺序；
- nullable；
- 主键、外键和必要物理约束；
- 宽表分块信息；
- Schema 版本或哈希。

`schema_doc` 不保存：

- 表或字段的业务描述；
- 中文别名；
- 指标口径；
- 业务规则；
- 人工确认但数据库中不存在的业务关系。

### 2.2 `semantic_doc` 只保存业务语义

| `doc_type` | 职责 |
|---|---|
| `model` | 表的业务含义、别名和适用场景 |
| `column` | 字段的业务含义、别名和安全属性 |
| `metric` | 指标定义、表达式和默认过滤 |
| `relationship` | 经过确认的业务关联关系 |
| `rule` | 上下文业务规则 |
| `global_rule` | 全局业务规则 |
| `example` | 自然语言问题与 SQL 示例 |

### 2.3 物理 Schema 是最终权威来源

`semantic_doc` 只能帮助选择表和字段，不能证明某个表或字段真实存在。SQL 生成使用的表名、字段名、类型、主键和外键必须来自 `schema_doc`。

## 3. Schema 文档模型

### 3.1 普通表

字段数不超过阈值时，保持一张表一条 `table` 文档。`content` 包含完整物理结构，`metadata` 保存对应的结构化快照。

```yaml
doc_type: table
table_name: publication
content: |
  表 publication
  字段：
  - pid integer [主键]
  - title text
  - year integer
  - citation_num integer
  - jid integer
  外键：
  - jid -> journal.jid
metadata:
  chunked: false
  column_count: 5
  schema_hash: "<hash>"
  columns:
    - name: pid
      type: integer
      ordinal: 1
      nullable: false
      primary_key: true
    - name: title
      type: text
      ordinal: 2
      nullable: true
  foreign_keys:
    - column: jid
      ref_table: journal
      ref_column: jid
```

### 3.2 宽表父文档

超过阈值时，生成一条轻量 `table` 父文档。

```yaml
doc_type: table
table_name: huge_order
content: |
  表 huge_order
  字段数：180
  主键：order_id
  外键：
  - customer_id -> customer.id
  - product_id -> product.id
metadata:
  chunked: true
  column_count: 180
  chunk_count: 8
  schema_hash: "<hash>"
  columns:
    - name: order_id
      type: integer
      ordinal: 1
      nullable: false
      primary_key: true
    - name: customer_id
      type: integer
      ordinal: 2
      nullable: false
    - name: paid_amount
      type: decimal
      ordinal: 35
      nullable: true
  foreign_keys:
    - column: customer_id
      ref_table: customer
      ref_column: id
  column_groups:
    - chunk_index: 1
      start_ordinal: 1
      end_ordinal: 25
    - chunk_index: 2
      start_ordinal: 26
      end_ordinal: 50
```

要求：

- 父文档 `content` 不重复全部字段；
- 父文档 `metadata.columns` 包含完整字段结构；
- 完整 metadata 不参与 embedding 和全文检索；
- `metadata.columns` 是离线生成的权威物理 Schema 快照。

### 3.3 宽表字段块

宽表生成多条 `column_group` 文档。

```yaml
doc_type: column_group
table_name: huge_order
content: |
  表 huge_order，字段组 2：
  - payment_method text
  - paid_amount decimal
  - paid_at timestamp
  - refund_amount decimal
metadata:
  parent_table: huge_order
  chunk_index: 2
  start_ordinal: 26
  end_ordinal: 50
  schema_hash: "<hash>"
  columns:
    - payment_method
    - paid_amount
    - paid_at
    - refund_amount
```

字段块只保存物理字段定义，不保存业务描述。

## 4. 宽表分块规则

### 4.1 默认阈值

初始默认值：

```python
SCHEMA_INLINE_MAX_COLUMNS = 50
SCHEMA_FULL_EXPAND_MAX_COLUMNS = 120
SCHEMA_COLUMN_GROUP_SIZE = 25
SCHEMA_MAX_COLUMNS_PER_TABLE = 60
```

| 字段数量 | 存储方式 | SQL 生成时展开方式 |
|---:|---|---|
| `<= 50` | 单条完整 `table` | 全部字段 |
| `51～120` | 父 `table` + `column_group` | 候选表命中后默认展开全部字段 |
| `> 120` | 父 `table` + `column_group` | 只展开命中字段组和必要字段 |

所有阈值必须配置化。

### 4.2 分块优先级

第一版采用确定性物理分块：

1. 保持字段原始顺序；
2. 单个字段定义不可拆开；
3. 每块最多约 25 个字段；
4. 嵌套字段或具有相同物理前缀的字段尽量放在同一块；
5. 主键和外键记录在父文档 metadata，不依赖字段块发现。

第一版不使用业务描述决定物理分块，避免 `schema_doc` 依赖 `semantic_doc`。后续可以在不改变物理内容的前提下，引入 semantic 分组作为召回提示。

## 5. 完整 Schema 的保存与读取

宽表父文档的 `metadata` 必须保存完整字段名和类型，确保系统能够：

- 在需要时完整展开该表；
- 不依赖向量 Top-K 还原 Schema；
- 验证 semantic 表和字段是否真实存在；
- 按字段预算构造裁剪后的物理 Schema。

完整 metadata 至少包含：

```text
字段名、字段类型、字段顺序、nullable、primary_key、外键、必要约束、schema_hash
```

完整 metadata 不包含业务描述。

## 6. 检索结果轻量化

当前向量和关键词检索使用 `SELECT *`。父 metadata 包含数百个字段后，召回阶段不能继续返回完整 metadata。

检索阶段只返回：

```text
id、db_id、doc_type、table_name、content、检索分数、必要的轻量定位字段
```

检索阶段不返回：

```text
完整 metadata.columns、embedding、tsv
```

候选表确定后，再通过精确查询加载完整 metadata。

建议接口：

```python
async def search_schema_docs(...) -> list[dict]:
    """轻量检索，不返回完整 metadata。"""

async def fetch_schema_tables(db_id: str, table_names: list[str]) -> list[dict]:
    """按表名读取完整 table 文档及 metadata。"""

async def fetch_schema_groups(
    db_id: str,
    table_names: list[str],
    chunk_indexes: dict[str, list[int]] | None = None,
) -> list[dict]:
    """按表名和块编号精确读取字段块。"""
```

## 7. 第一阶段：候选表召回

候选表由三路产生。

### 7.1 Semantic 表召回

从 `semantic_doc` 中单独检索 `doc_type=model`，根据业务含义召回候选表。

### 7.2 Schema 父表召回

检索 `schema_doc` 中的 `doc_type=table`，根据真实表名、主键和外键等物理信息召回表。

### 7.3 Schema 字段块召回

检索 `schema_doc` 中的 `doc_type=column_group`。字段块命中后，通过 `table_name` 或 `metadata.parent_table` 反向归并到父表。

### 7.4 表级分数融合

同一张表可能被多个字段块命中。不能累加该表所有字段块的分数，否则宽表会因块数更多获得不公平优势。

每张表在每个通道只保留最佳排名或最佳得分：

```python
schema_group_score = max(group_scores_for_table)
```

再融合以下排名：

- semantic model 排名；
- schema table 排名；
- 最佳 column_group 排名。

最终按 `table_name` 去重，默认最多保留 8 张表：

```python
SCHEMA_FINAL_TABLE_TOP_K = 8
SEMANTIC_MODEL_TOP_K = 5
```

## 8. 超宽候选表的字段裁剪与字段块选择

本阶段不是所有候选表的通用步骤，只在候选表字段数超过 `SCHEMA_FULL_EXPAND_MAX_COLUMNS` 时执行：

```python
needs_column_selection = column_count > SCHEMA_FULL_EXPAND_MAX_COLUMNS
```

处理规则：

- 普通表（`column_count <= SCHEMA_INLINE_MAX_COLUMNS`）跳过本阶段，直接加载全部字段；
- 中等宽表（`SCHEMA_INLINE_MAX_COLUMNS < column_count <= SCHEMA_FULL_EXPAND_MAX_COLUMNS`）跳过本阶段，从父文档 metadata 加载全部字段；
- 超宽表（`column_count > SCHEMA_FULL_EXPAND_MAX_COLUMNS`）进入本阶段，只选择相关字段组和必要字段。

本阶段的目的，是在已经确定要使用某张超宽表后，决定将该表的哪些字段放入 `linked_schema`，避免把数百个字段全部送入 SQL 生成提示词。

超宽表的字段来源包括：

1. `semantic_doc.column` 命中的字段；
2. `semantic_doc.metric.expression` 涉及的字段；
3. `semantic_doc.relationship.condition` 涉及的字段；
4. `schema_doc.column_group` 命中的字段块；
5. 问题中直接出现的真实字段名；
6. 当前 JOIN 路径必需的主外键字段。

超宽表字段块检索必须限制为：

```text
db_id = 当前数据库
table_name IN 候选表
doc_type = column_group
```

选出的业务字段必须先使用 `table_name + column_name` 在父文档 `metadata.columns` 中验证。验证通过后，再定位字段所属的 `column_group`。最终字段集合还必须无条件补齐当前 SQL 所需的主键和外键。

## 9. 字段展开规则

### 9.1 普通表

跳过第 8 节的字段裁剪，直接加载全部字段。

### 9.2 中等宽表

字段数为 51～120 时：

- 检索阶段使用字段块；
- 候选表确定后，从父 metadata 加载全部字段；
- 字段块用于发现表，不负责最终完整性。
- 跳过第 8 节的字段裁剪。

### 9.3 超宽表

字段数超过 120 时，执行第 8 节的字段裁剪与字段块选择，初始加载：

- 命中的字段组；
- semantic column 命中的字段；
- metric expression 涉及的字段；
- 主键；
- 当前 JOIN 路径涉及的外键；
- SELECT、WHERE、GROUP BY 和 ORDER BY 推断所需字段。

默认每张表最多加载 60 个普通字段，主键、外键和其他必要字段不受普通字段预算限制。

如果没有字段块命中：

- 计数类问题至少提供主键；
- 在候选表内部执行一次字段块检索；
- 低置信度时扩大字段预算；
- 不随机选择字段。

## 10. 物理 Schema 拼装

向量或关键词召回只负责定位，最终 Schema 必须通过精确读取生成：

```text
候选表名
→ 精确加载 table.metadata
→ 确定需要的字段
→ 按原 ordinal 排序
→ 补齐主键和外键
→ 构造 linked_schema
```

宽表裁剪后的示例：

```sql
CREATE TABLE huge_order (
  order_id integer PRIMARY KEY,
  customer_id integer,
  payment_method text,
  paid_amount decimal,
  paid_at timestamp,
  FOREIGN KEY (customer_id) REFERENCES customer(id)
);
```

生成提示词必须明确：

```text
以下 Schema 可能是宽表经过字段选择后的子集。
只能使用其中出现的表和字段。
主键、外键及当前 JOIN 所需字段已经补齐。
```

## 11. Semantic 与物理 Schema 的映射

映射键：

```text
db_id + table_name
db_id + table_name + column_name
```

处理流程：

```text
semantic_doc.model
→ 找到业务候选表
→ 用 table_name 精确加载 schema_doc.table

semantic_doc.column
→ 找到业务候选字段
→ 用 table_name + column_name 在 table.metadata 中验证
→ 定位对应字段块
```

如果 semantic 中的表或字段在物理 Schema 中不存在：

- 不得进入 `linked_schema`；
- 记录结构化日志；
- 将 semantic 文档视为过期或错误数据。

## 12. 降级兼容

### 12.1 Semantic layer 关闭

当 `CONTEXT_LAYER_ENABLED=false` 时，使用 `schema_doc.table` 和 `schema_doc.column_group` 完成召回。业务语义能力下降，但主链路仍应运行。

### 12.2 宽表功能关闭

增加开关：

```python
SCHEMA_CHUNKING_ENABLED = True
```

关闭时保持当前一表一条完整文档的行为，用于 A/B 测试和回滚。

### 12.3 旧数据兼容

不存在 `chunked`、`column_count`、`columns` 或 `column_groups` metadata 时，按照旧版单表完整文档处理。

## 13. Schema 更新一致性

每张表及其字段块保存相同的 `schema_hash`。

重新灌入时：

- 同一 `db_id + table_name` 的父文档和字段块必须一起替换；
- 不允许新父文档与旧字段块混用；
- 精确读取时发现 hash 不一致，应忽略不一致字段块并记录错误；
- 推荐以单个 `db_id` 为事务单位完成删除和重灌。

## 14. 数据库表结构与索引

本方案原则上不改变现有 `schema_doc` 的关系型表结构。现有字段已经能够承载父表文档和字段块：

```text
db_id
doc_type
table_name
content
metadata JSONB
embedding
tsv
```

实施后的变化仅包括：

- `doc_type` 增加新的业务取值 `column_group`；
- `metadata` JSONB 增加 `chunked`、`column_count`、`columns`、`foreign_keys`、`column_groups` 和 `schema_hash` 等结构；
- 同一张宽表由一条 `table` 记录和多条 `column_group` 记录共同表示。

本方案不要求：

- 新建 Schema 存储表；
- 为完整字段结构增加独立数据库列；
- 修改 `semantic_doc` 表结构；
- 修改被查询业务数据库的任何表结构。

为支持候选表确定后的精确读取，应检查现有数据库是否已经存在适合以下条件的复合索引：

```text
db_id + doc_type + table_name
```

如果不存在，实施时通过 Alembic 增加索引。该迁移属于查询性能优化，不是父表和字段块数据模型成立的必要条件。

实施完成后必须重新生成并入库 `schema_doc`，因为旧数据不包含父文档完整 metadata、`column_group` 文档和新的 embedding。`semantic_doc` 内容未变化时不要求重建；使用 Elasticsearch 时还必须同步重建对应的 Schema 搜索索引。

## 15. 计划修改范围

实施时预计涉及：

- Schema 文档构建和 ingest；
- 向量、PostgreSQL 关键词和 Elasticsearch 关键词检索；
- semantic model/column 与物理 Schema 的融合；
- LangGraph 状态、候选表选择和 Schema 拼装；
- 配置、日志、单元测试和离线评测。

## 16. 非目标

本 Spec 暂不包括：

- 自动生成或修改业务描述；
- 自动修复过期 semantic_doc；
- 基于真实数据值进行枚举值召回；
- 自动推断未经确认的业务 JOIN；
- 修改 SQL Guard、缓存策略或自然语言答案生成。

## 17. 测试要求

### 17.1 文档构建

- 小表仍生成一条完整 `table`；
- 宽表生成一条父 `table` 和多个 `column_group`；
- 父 metadata 包含全部字段及类型；
- 字段顺序与源 Schema 一致；
- 所有字段恰好归属一个字段块；
- 父子 `schema_hash` 一致；
- 主外键完整保留。

### 17.2 召回

- 命中父文档可以召回表；
- 命中字段块可以反向召回父表；
- 多个字段块不会因分数累加让宽表获得不公平优势；
- semantic model 命中的表能进入物理 Schema；
- semantic column 能映射到真实字段；
- 不存在的 semantic 表或字段被拒绝。

### 17.3 拼装

- 小表输出完整 Schema；
- 中等宽表命中后输出完整 Schema；
- 超宽表只输出相关字段和必要键；
- 输出字段保持原始顺序；
- JOIN 外键始终补齐；
- 不会输出物理 Schema 中不存在的字段。

### 17.4 兼容性

- 关闭 semantic layer 后仍能运行；
- 关闭 Schema chunking 后行为与旧版一致；
- 旧版 schema_doc 数据仍可读取；
- PostgreSQL 和 Elasticsearch 检索行为保持一致。

## 18. 验收指标

实施后至少对比：

- 表严格召回率；
- 字段严格召回率；
- SQL 执行准确率；
- 每次请求 `linked_schema` token 数；
- Schema 检索延迟；
- PostgreSQL 返回数据量；
- semantic 独立挽救的查询数量；
- 宽表误召回率；
- 宽表因字段裁剪导致的失败数量。

验收原则：

- 表召回率不能低于当前版本；
- 普通表 SQL 执行准确率不能明显下降；
- 宽表 prompt token 数应显著下降；
- semantic model 命中的合法表必须能够进入物理 Schema；
- 关闭新功能时能够恢复旧行为。

## 19. 实施约束

本文档当前仍为草案。只有在用户明确确认 Spec 并明确要求“实施 Spec”后，才允许根据本文档修改代码、迁移或运行具有实现副作用的命令。
