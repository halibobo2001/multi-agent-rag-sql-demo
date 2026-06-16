from __future__ import annotations

from pathlib import Path

import pandas as pd

from agentic_analytics_demo.agents import AnalyticsAgentSystem
from agentic_analytics_demo.llm import GeminiClient
from agentic_analytics_demo.rag import SchemaRAG
from agentic_analytics_demo.sql_guard import validate_sql
from agentic_analytics_demo.viz import normalize_chart_spec, render_plotly_chart
from agentic_analytics_demo.warehouse import create_retailrocket_warehouse, get_schema


def write_sample_dataset(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            [1433221332117, 257597, "view", 355908, None],
            [1433224214164, 992329, "view", 248676, None],
            [1433225000000, 257597, "addtocart", 355908, None],
            [1433226000000, 257597, "transaction", 355908, 4000],
            [1433311332117, 300001, "view", 248676, None],
            [1433312332117, 300002, "view", 111111, None],
            [1433313332117, 300002, "addtocart", 111111, None],
        ],
        columns=["timestamp", "visitorid", "event", "itemid", "transactionid"],
    ).to_csv(root / "events.csv", index=False)
    pd.DataFrame([[100, None], [200, 100]], columns=["categoryid", "parentid"]).to_csv(
        root / "category_tree.csv", index=False
    )
    pd.DataFrame(
        [
            [1433041200000, 355908, "categoryid", "200"],
            [1433041200000, 248676, "categoryid", "100"],
            [1433041200000, 111111, "available", "1"],
        ],
        columns=["timestamp", "itemid", "property", "value"],
    ).to_csv(root / "item_properties_part1.csv", index=False)
    pd.DataFrame(
        [
            [1433041200000, 111111, "categoryid", "200"],
            [1433041200000, 355908, "available", "1"],
            [1433041200000, 248676, "available", "1"],
        ],
        columns=["timestamp", "itemid", "property", "value"],
    ).to_csv(root / "item_properties_part2.csv", index=False)


def test_warehouse_creates_core_tables(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    write_sample_dataset(dataset_dir)
    db_path = tmp_path / "demo.sqlite"
    create_retailrocket_warehouse(db_path, dataset_dir, chunksize=3)
    schema = get_schema(db_path)
    assert {"events", "category_tree", "item_latest_category", "item_latest_availability"} <= set(schema)
    assert "visitorid" in schema["events"]


def test_rag_returns_relevant_context(tmp_path: Path) -> None:
    rag = SchemaRAG(tmp_path / "chroma")
    rag.ensure_index()
    contexts = rag.retrieve("哪些品类的加购到购买转化率最高", top_k=3)
    assert contexts
    joined = " ".join(ctx.text for ctx in contexts).lower()
    assert "category" in joined or "addtocart" in joined or "transaction" in joined


def test_sql_validator_allows_select_and_adds_limit(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    write_sample_dataset(dataset_dir)
    db_path = tmp_path / "demo.sqlite"
    create_retailrocket_warehouse(db_path, dataset_dir, chunksize=3)
    result = validate_sql("SELECT event, COUNT(*) AS events FROM events GROUP BY event", db_path)
    assert result.ok
    assert "LIMIT" in result.sql.upper()


def test_sql_validator_blocks_mutation(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    write_sample_dataset(dataset_dir)
    db_path = tmp_path / "demo.sqlite"
    create_retailrocket_warehouse(db_path, dataset_dir, chunksize=3)
    result = validate_sql("DROP TABLE events", db_path)
    assert not result.ok


def test_chart_spec_normalization_and_render() -> None:
    df = pd.DataFrame({"itemid": [355908, 248676], "views": [21, 19]})
    spec = normalize_chart_spec(df, {"type": "bar", "x": "itemid", "y": "views"})
    fig = render_plotly_chart(df, spec)
    assert spec["x"] == "itemid"
    assert fig.data


def test_agent_pipeline_with_fallback_llm(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dataset"
    write_sample_dataset(dataset_dir)
    db_path = tmp_path / "demo.sqlite"
    create_retailrocket_warehouse(db_path, dataset_dir, chunksize=3)
    rag = SchemaRAG(tmp_path / "chroma")
    rag.ensure_index()
    system = AnalyticsAgentSystem(db_path, rag, GeminiClient(api_key=""))
    result = system.run("哪些商品浏览量最高？")
    assert not result.error
    assert "SELECT" in result.sql.upper()
    assert not result.dataframe.empty
    assert result.analysis
    assert any("SQL Validator" in item for item in result.trace)
