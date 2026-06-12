from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


DEFAULT_CHART = {"type": "bar", "title": "分析结果"}


def normalize_chart_spec(dataframe: pd.DataFrame, raw_spec: dict[str, Any] | None) -> dict[str, Any]:
    spec = dict(DEFAULT_CHART)
    if isinstance(raw_spec, dict):
        spec.update(raw_spec)

    columns = list(dataframe.columns)
    if not columns:
        return spec

    numeric_columns = [col for col in columns if pd.api.types.is_numeric_dtype(dataframe[col])]
    spec["x"] = spec.get("x") if spec.get("x") in columns else columns[0]
    if spec.get("y") not in columns:
        spec["y"] = numeric_columns[0] if numeric_columns else columns[-1]
    if spec.get("color") not in columns:
        spec.pop("color", None)
    if spec.get("type") not in {"bar", "line", "scatter", "pie", "table"}:
        spec["type"] = "bar"
    return spec


def render_plotly_chart(dataframe: pd.DataFrame, chart_spec: dict[str, Any] | None = None) -> go.Figure:
    if dataframe.empty:
        fig = go.Figure()
        fig.update_layout(title="没有可视化数据")
        return fig

    spec = normalize_chart_spec(dataframe, chart_spec)
    chart_type = spec["type"]
    title = spec.get("title", "分析结果")
    x = spec.get("x")
    y = spec.get("y")
    color = spec.get("color")

    if chart_type == "line":
        return px.line(dataframe, x=x, y=y, color=color, title=title, markers=True)
    if chart_type == "scatter":
        return px.scatter(dataframe, x=x, y=y, color=color, title=title)
    if chart_type == "pie":
        return px.pie(dataframe, names=x, values=y, title=title)
    if chart_type == "table":
        return go.Figure(
            data=[
                go.Table(
                    header={"values": list(dataframe.columns)},
                    cells={"values": [dataframe[col] for col in dataframe.columns]},
                )
            ]
        )
    return px.bar(dataframe, x=x, y=y, color=color, title=title)

