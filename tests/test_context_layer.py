from pathlib import Path

from app.core.context_layer.compiler import compile_fewshots, compile_semantic_docs
from app.core.context_layer.parser import load_context_bundle, parse_rules_markdown, parse_sql_markdown
from app.core.context_layer.validator import validate_sql_semantics


def test_parse_rules_markdown_splits_global_and_contextual():
    sections = parse_rules_markdown(
        """
## global
- 默认排除测试数据

## contextual
- 客户分析优先使用 customers
"""
    )

    assert sections["global"] == ["默认排除测试数据"]
    assert sections["contextual"] == ["客户分析优先使用 customers"]


def test_parse_sql_markdown_front_matter():
    parsed = parse_sql_markdown(
        """---
db_id: demo
question: 销售额是多少？
source: manual
---
```sql
SELECT 1
```
"""
    )

    assert parsed["db_id"] == "demo"
    assert parsed["question"] == "销售额是多少？"
    assert parsed["source"] == "manual"
    assert parsed["sql"] == "SELECT 1;"


def test_compile_context_bundle_to_semantic_docs(tmp_path: Path):
    root = tmp_path / "context" / "demo"
    (root / "sql").mkdir(parents=True)
    (root / "models.yaml").write_text(
        """
db_id: demo
models:
  - table: orders
    description: 订单表
    columns:
      - name: internal_note
        hidden: true
      - name: phone
        sensitive: true
""",
        encoding="utf-8",
    )
    (root / "metrics.yaml").write_text(
        """
db_id: demo
metrics:
  - name: revenue
    alias: 销售额
    expression: SUM(order_items.amount)
    default_filters:
      - orders.status = 'completed'
""",
        encoding="utf-8",
    )
    (root / "relationships.yaml").write_text(
        """
db_id: demo
relationships:
  - name: orders_customers
    models: [orders, customers]
    condition: orders.customer_id = customers.id
    approved: true
""",
        encoding="utf-8",
    )
    (root / "rules.md").write_text("## global\n- 默认只看完成订单\n\n## contextual\n- 趋势默认按月\n", encoding="utf-8")
    (root / "sql" / "revenue.md").write_text(
        "---\ndb_id: demo\nquestion: 销售额是多少？\nsource: manual\n---\nSELECT 1;",
        encoding="utf-8",
    )

    bundle = load_context_bundle(tmp_path / "context", "demo")
    docs = compile_semantic_docs(bundle)
    fewshots = compile_fewshots(bundle)

    assert {d["doc_type"] for d in docs} >= {"model", "column", "metric", "relationship", "global_rule", "rule", "example"}
    hidden = next(d for d in docs if d["name"] == "orders.internal_note")
    assert hidden["payload"]["hidden"] is True
    metric = next(d for d in docs if d["doc_type"] == "metric")
    assert "销售额" in metric["content"]
    assert fewshots[0]["metadata"]["source"] == "manual"


def test_validate_semantics_flags_hidden_join_and_default_filter():
    docs = [
        {"doc_type": "column", "name": "orders.internal_note", "payload": {"table": "orders", "name": "internal_note", "hidden": True}},
        {"doc_type": "relationship", "name": "orders_customers", "payload": {"models": ["orders", "customers"], "approved": True}},
        {"doc_type": "metric", "name": "revenue", "payload": {"default_filters": ["orders.status = 'completed'"]}},
    ]

    result = validate_sql_semantics(
        "SELECT orders.internal_note, SUM(order_items.amount) FROM orders JOIN order_items ON orders.id = order_items.order_id",
        docs,
    )

    assert not result.ok
    assert any("隐藏字段" in w for w in result.warnings)
    assert any("未审批 JOIN" in w for w in result.warnings)
    assert any("默认过滤" in w for w in result.warnings)
