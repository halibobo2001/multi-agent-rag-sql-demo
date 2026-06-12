from __future__ import annotations

from pathlib import Path

import pandas as pd

from agentic_analytics_demo.agents import AnalyticsAgentSystem
from agentic_analytics_demo.llm import GeminiClient
from agentic_analytics_demo.rag import SchemaRAG
from agentic_analytics_demo.sql_guard import validate_sql
from agentic_analytics_demo.viz import normalize_chart_spec, render_plotly_chart
from agentic_analytics_demo.warehouse import create_demo_warehouse, get_schema


def test_warehouse_creates_core_tables(tmp_path: Path) -> None:
    db_path = tmp_path / "demo.sqlite"
    create_demo_warehouse(db_path)
    schema = get_schema(db_path)
    assert {"users", "sessions", "events", "conversions", "experiments"} <= set(schema)
    assert "country" in schema["users"]


def test_rag_returns_relevant_context(tmp_path: Path) -> None:
    rag = SchemaRAG(tmp_path / "chroma")
    rag.ensure_index()
    contexts = rag.retrieve("德国用户转化率按国家分析", top_k=3)
    assert contexts
    joined = " ".join(ctx.text for ctx in contexts).lower()
    assert "country" in joined or "conversion" in joined


def test_sql_validator_allows_select_and_adds_limit(tmp_path: Path) -> None:
    db_path = tmp_path / "demo.sqlite"
    create_demo_warehouse(db_path)
    result = validate_sql("SELECT country, COUNT(*) AS users FROM users GROUP BY country", db_path)
    assert result.ok
    assert "LIMIT" in result.sql.upper()


def test_sql_validator_blocks_mutation(tmp_path: Path) -> None:
    db_path = tmp_path / "demo.sqlite"
    create_demo_warehouse(db_path)
    result = validate_sql("DROP TABLE users", db_path)
    assert not result.ok


def test_chart_spec_normalization_and_render() -> None:
    df = pd.DataFrame({"country": ["Sweden", "Germany"], "conversion_rate_pct": [21.2, 19.4]})
    spec = normalize_chart_spec(df, {"type": "bar", "x": "country", "y": "conversion_rate_pct"})
    fig = render_plotly_chart(df, spec)
    assert spec["x"] == "country"
    assert fig.data


def test_agent_pipeline_with_fallback_llm(tmp_path: Path) -> None:
    db_path = tmp_path / "demo.sqlite"
    create_demo_warehouse(db_path)
    rag = SchemaRAG(tmp_path / "chroma")
    rag.ensure_index()
    system = AnalyticsAgentSystem(db_path, rag, GeminiClient(api_key=""))
    result = system.run("本月哪些国家转化率最高？")
    assert not result.error
    assert "SELECT" in result.sql.upper()
    assert not result.dataframe.empty
    assert result.analysis
    assert any("SQL Validator" in item for item in result.trace)

