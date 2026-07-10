"""文件式语义层解析。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ContextBundle:
    db_id: str
    models: list[dict[str, Any]] = field(default_factory=list)
    metrics: list[dict[str, Any]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    global_rules: list[str] = field(default_factory=list)
    contextual_rules: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)


def load_context_bundle(context_root: str | Path, db_id: str) -> ContextBundle:
    """读取 context/<db_id> 下的 YAML/Markdown 语义层文件。"""
    root = Path(context_root) / db_id
    bundle = ContextBundle(db_id=db_id)
    if not root.exists():
        raise FileNotFoundError(f"找不到语义层目录: {root}")

    models = _load_yaml(root / "models.yaml")
    if models:
        _assert_db_id(models, db_id, "models.yaml")
        bundle.models = list(models.get("models") or [])

    metrics = _load_yaml(root / "metrics.yaml")
    if metrics:
        _assert_db_id(metrics, db_id, "metrics.yaml")
        bundle.metrics = list(metrics.get("metrics") or [])

    relationships = _load_yaml(root / "relationships.yaml")
    if relationships:
        _assert_db_id(relationships, db_id, "relationships.yaml")
        bundle.relationships = list(relationships.get("relationships") or [])

    rules_path = root / "rules.md"
    if rules_path.exists():
        sections = parse_rules_markdown(rules_path.read_text(encoding="utf-8"))
        bundle.global_rules = sections["global"]
        bundle.contextual_rules = sections["contextual"]

    sql_dir = root / "sql"
    if sql_dir.exists():
        bundle.examples = [parse_sql_markdown(p.read_text(encoding="utf-8"), p.name, db_id) for p in sorted(sql_dir.glob("*.md"))]
    return bundle


def parse_rules_markdown(text: str) -> dict[str, list[str]]:
    """解析 rules.md 中的 ## global / ## contextual 规则。"""
    current: str | None = None
    sections = {"global": [], "contextual": []}
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("##"):
            name = line.lstrip("#").strip().lower()
            current = name if name in sections else None
            continue
        if current in sections:
            sections[current].append(line[2:].strip() if line.startswith("- ") else line)
    return sections


def parse_sql_markdown(text: str, filename: str = "<memory>", default_db_id: str | None = None) -> dict[str, Any]:
    """解析带 front matter 的 confirmed NL->SQL markdown。"""
    meta: dict[str, Any] = {}
    body = text.strip()
    if body.startswith("---"):
        parts = body.split("---", 2)
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[1]) or {}
            body = parts[2].strip()
    sql = _strip_code_fence(body)
    question = str(meta.get("question") or "").strip()
    if not question:
        raise ValueError(f"{filename} 缺少 front matter question")
    return {
        "db_id": str(meta.get("db_id") or default_db_id or "").strip(),
        "question": question,
        "sql": sql,
        "source": str(meta.get("source") or "manual").strip(),
        "filename": filename,
    }


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} 必须是 YAML object")
    return data


def _assert_db_id(data: dict[str, Any], db_id: str, filename: str) -> None:
    actual = data.get("db_id")
    if actual and actual != db_id:
        raise ValueError(f"{filename} db_id={actual} 与目录 db_id={db_id} 不一致")


def _strip_code_fence(sql: str) -> str:
    sql = sql.strip()
    if sql.startswith("```"):
        lines = sql.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        sql = "\n".join(lines)
    return sql.strip().rstrip(";").strip() + ";"
