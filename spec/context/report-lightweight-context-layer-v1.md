# QueryForge 轻量语义层 v1 实施报告

## 背景

本次演进在代码实现前没有先把最终版 spec 落盘，这是流程问题。当前已补充实施版 spec：

- `spec/context/lightweight-context-layer-v1-implementation-spec.md`

本报告记录本次已经完成的代码变更、验证情况和遗留风险。

## 已完成变更

### 语义层数据模型

- 新增 Alembic 迁移 `0006_semantic_context_layer.py`。
- 新增 `semantic_doc` 表，用于存储文件式语义层编译后的可检索文档。
- 给 `fewshot_example` 增加 `metadata JSONB`，用于区分 `cspider`、`manual`、`learned` 来源。

### 文件式 context 解析与编译

新增 `app/core/context_layer/`：

- `parser.py`：读取 `context/<db_id>/` 下的 YAML / Markdown。
- `compiler.py`：把 models、metrics、relationships、rules、confirmed SQL examples 编译成 `semantic_doc` rows 和 few-shot rows。
- `retriever.py`：按 `db_id` 检索语义上下文，精确加载 global rules、relationships、columns。
- `validator.py`：执行轻量 SQL 语义校验。

新增命令：

```bash
python -m eval.ingest_context --db-id concert_singer --replace
make ingest-context DB_ID=concert_singer
```

### LangGraph 链路接入

新增节点：

- `retrieve_semantics`
- `validate_semantics`

链路已调整为：

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

### Prompt 改造

`GENERATE_SQL_PROMPT` 新增：

- `# 全局业务规则`
- `# 命中的业务语义`
- `# 审批连接路径`

`generate_sql` 节点会从 `GraphState` 注入：

- `global_rules`
- `semantic_context`
- `approved_relationships`

### 配置项

新增配置：

```text
CONTEXT_LAYER_ENABLED=false
CONTEXT_DIR=context
SQL_SEMANTIC_VALIDATE_ENABLED=false
SQL_SEMANTIC_VALIDATE_MODE=warn
```

已同步到：

- `.env.example`
- `.env.production.example`

### 样例 context

新增 `context/concert_singer/`：

- `models.yaml`
- `metrics.yaml`
- `relationships.yaml`
- `rules.md`
- `sql/count_singers.md`

该样例只用于验证语义层机制，不作为真实企业 BI demo。

### 测试

新增 `tests/test_context_layer.py`，覆盖：

- rules markdown 解析。
- confirmed SQL markdown 解析。
- context bundle 编译。
- hidden/sensitive/approved join/default filter 语义校验。

## 验证情况

已执行：

```bash
C:\Users\Dksheep\anaconda3\python.exe -m compileall app\core\context_layer app\core\langgraph\nodes eval\ingest_context.py
```

结果：通过。

尝试执行：

```bash
C:\Users\Dksheep\anaconda3\python.exe -m pytest tests/test_context_layer.py -q
```

结果：失败，原因是当前 Python 环境缺少项目依赖 `sqlglot`：

```text
ModuleNotFoundError: No module named 'sqlglot'
```

该失败属于环境依赖未安装，不是新增测试收集阶段的语法错误。需要在安装项目依赖后重新运行。

## 遗留风险与后续建议

- 当前 `validate_semantics` 的 join 检查是轻量实现，只检查表对，不做完整 join condition 等价判断。
- metric default filter 检查采用字符串紧凑匹配，对 SQL 等价改写不够鲁棒。
- `semantic_doc` 的 ES 同步尚未扩展；当前 pg_jieba/pgvector 路径可用，ES 镜像需要后续适配。
- `ingest_context --replace` 依赖 DB 迁移已执行，否则 `semantic_doc` 和 `fewshot_example.metadata` 不存在。
- Northwind / AdventureWorksDW 未接入，本次仅完成语义层机制，不承诺公开 BI 数据源无缝接入。
- 当前 report 记录的是已完成实现；如果后续继续扩展 BI demo-data，应另开 spec。

## 建议下一步

1. 安装依赖后运行：

```bash
pytest tests/test_context_layer.py -q
```

2. 执行迁移：

```bash
make migrate
```

3. 编译样例 context：

```bash
make ingest-context DB_ID=concert_singer
```

4. 开启配置验证链路：

```text
CONTEXT_LAYER_ENABLED=true
SQL_SEMANTIC_VALIDATE_ENABLED=true
SQL_SEMANTIC_VALIDATE_MODE=warn
```
