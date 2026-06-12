from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

from .rag import RetrievedContext


@dataclass(frozen=True)
class SQLGeneration:
    sql: str
    chart_spec: dict[str, Any]
    rationale: str


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str = "gemini-3.5-flash"):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
        self._client = None
        if self.api_key:
            try:
                from google import genai

                self._client = genai.Client(api_key=self.api_key)
            except Exception:
                self._client = None

    @property
    def is_live(self) -> bool:
        return self._client is not None

    def generate_sql(
        self,
        question: str,
        contexts: list[RetrievedContext],
        previous_error: str | None = None,
    ) -> SQLGeneration:
        if not self.is_live:
            return fallback_sql_generation(question)

        prompt = _build_sql_prompt(question, contexts, previous_error)
        response = self._client.models.generate_content(model=self.model, contents=prompt)
        payload = _extract_json(getattr(response, "text", ""))
        if not payload.get("sql"):
            return fallback_sql_generation(question)
        return SQLGeneration(
            sql=str(payload["sql"]),
            chart_spec=payload.get("chart_spec") or {"type": "bar", "title": "分析结果"},
            rationale=str(payload.get("rationale", "Gemini generated SQL.")),
        )

    def analyze(self, question: str, sql: str, dataframe: pd.DataFrame) -> str:
        if dataframe.empty:
            return "查询成功，但没有返回符合条件的数据。可以尝试放宽时间范围或筛选条件。"
        if not self.is_live:
            return fallback_analysis(question, dataframe)

        preview = dataframe.head(20).to_markdown(index=False)
        prompt = (
            "你是企业级数据分析 Agent。请用中文给出 3-5 句简洁业务洞察，指出趋势、异常和可能行动。\n"
            f"用户问题: {question}\nSQL:\n{sql}\n结果预览:\n{preview}\n"
        )
        response = self._client.models.generate_content(model=self.model, contents=prompt)
        return getattr(response, "text", "").strip() or fallback_analysis(question, dataframe)


def fallback_sql_generation(question: str) -> SQLGeneration:
    normalized = question.lower()
    if any(word in question for word in ["转化", "转化率"]) or "conversion" in normalized:
        return SQLGeneration(
            sql="""
            SELECT
                u.country,
                ROUND(AVG(c.converted) * 100, 2) AS conversion_rate_pct,
                COUNT(*) AS funnel_events,
                ROUND(SUM(c.revenue), 2) AS revenue
            FROM conversions c
            JOIN users u ON u.user_id = c.user_id
            WHERE DATE(c.occurred_at) >= DATE('2026-05-01')
            GROUP BY u.country
            ORDER BY conversion_rate_pct DESC
            """,
            chart_spec={"type": "bar", "x": "country", "y": "conversion_rate_pct", "title": "各国家本月转化率"},
            rationale="Fallback matched conversion-rate country analysis.",
        )
    if any(word in question for word in ["移动", "桌面", "设备", "mobile", "desktop", "漏斗"]):
        return SQLGeneration(
            sql="""
            SELECT
                s.device_type,
                c.funnel_step,
                ROUND(AVG(c.converted) * 100, 2) AS conversion_rate_pct,
                COUNT(*) AS attempts
            FROM sessions s
            JOIN conversions c ON c.session_id = s.session_id
            GROUP BY s.device_type, c.funnel_step
            ORDER BY c.funnel_step, s.device_type
            """,
            chart_spec={
                "type": "bar",
                "x": "funnel_step",
                "y": "conversion_rate_pct",
                "color": "device_type",
                "title": "不同设备的漏斗转化率",
            },
            rationale="Fallback matched device funnel analysis.",
        )
    if "德国" in question or "germany" in normalized:
        return SQLGeneration(
            sql="""
            SELECT
                e.feature,
                e.page,
                COUNT(*) AS event_count
            FROM events e
            JOIN sessions s ON s.session_id = e.session_id
            JOIN users u ON u.user_id = s.user_id
            WHERE u.country = 'Germany'
            GROUP BY e.feature, e.page
            ORDER BY event_count DESC
            """,
            chart_spec={"type": "bar", "x": "feature", "y": "event_count", "color": "page", "title": "德国用户功能访问"},
            rationale="Fallback matched Germany feature usage.",
        )
    if any(word in question for word in ["实验", "variant", "A/B", "ab", "收入"]):
        return SQLGeneration(
            sql="""
            SELECT
                e.experiment_name,
                e.variant,
                ROUND(AVG(c.converted) * 100, 2) AS conversion_rate_pct,
                ROUND(SUM(c.revenue), 2) AS total_revenue,
                COUNT(DISTINCT e.user_id) AS exposed_users
            FROM experiments e
            JOIN conversions c ON c.user_id = e.user_id
            WHERE c.funnel_step = 'paid'
            GROUP BY e.experiment_name, e.variant
            ORDER BY total_revenue DESC
            """,
            chart_spec={
                "type": "bar",
                "x": "variant",
                "y": "total_revenue",
                "color": "experiment_name",
                "title": "A/B 实验收入表现",
            },
            rationale="Fallback matched experiment revenue analysis.",
        )
    return SQLGeneration(
        sql="""
        SELECT
            DATE(started_at) AS activity_date,
            session_country AS country,
            COUNT(DISTINCT session_id) AS active_sessions
        FROM sessions
        WHERE DATE(started_at) >= DATE('2026-05-01')
        GROUP BY DATE(started_at), session_country
        ORDER BY activity_date, active_sessions DESC
        """,
        chart_spec={"type": "line", "x": "activity_date", "y": "active_sessions", "color": "country", "title": "活跃会话趋势"},
        rationale="Fallback defaulted to active session trend.",
    )


def fallback_analysis(question: str, dataframe: pd.DataFrame) -> str:
    row_count = len(dataframe)
    columns = ", ".join(map(str, dataframe.columns[:5]))
    lines = [f"本次查询返回 {row_count} 行结果，核心字段包括 {columns}。"]
    numeric_cols = [col for col in dataframe.columns if pd.api.types.is_numeric_dtype(dataframe[col])]
    if numeric_cols:
        metric = numeric_cols[0]
        top_row = dataframe.sort_values(metric, ascending=False).iloc[0]
        dimension = dataframe.columns[0]
        lines.append(f"按 {metric} 看，最高的 {dimension} 是 {top_row[dimension]}，数值为 {top_row[metric]}。")
    lines.append("这是 fallback 分析；配置 GEMINI_API_KEY 后会生成更自然的业务洞察和行动建议。")
    return " ".join(lines)


def _build_sql_prompt(question: str, contexts: list[RetrievedContext], previous_error: str | None) -> str:
    context_text = "\n\n".join(f"{ctx.title}\n{ctx.text}" for ctx in contexts)
    repair_text = f"\n上一次 SQL 错误: {previous_error}\n请修复。" if previous_error else ""
    return f"""
你是只读 SQLite 数据分析 SQL Agent。必须只输出 JSON，不要 Markdown。
目标：把用户中文问题转换为安全 SQLite SQL，并给出 Plotly 图表规格。

硬性规则：
1. 只能生成 SELECT 或 WITH 查询。
2. 禁止 INSERT/UPDATE/DELETE/DROP/ALTER/ATTACH/PRAGMA/CREATE。
3. 只能使用给定 Schema 中存在的表和字段。
4. SQL 不要包含注释。
5. 图表规格只允许 type/x/y/color/title 字段，type 为 bar/line/scatter/pie/table 之一。
6. 时间过滤必须使用业务事实表时间：转化/收入用 conversions.occurred_at，会话活跃用 sessions.started_at，功能事件用 events.occurred_at；只有注册分析才用 users.signup_date。

Schema 与指标上下文：
{context_text}

用户问题：
{question}
{repair_text}

返回 JSON 格式：
{{
  "sql": "SELECT ...",
  "chart_spec": {{"type": "bar", "x": "...", "y": "...", "title": "..."}},
  "rationale": "一句话解释"
}}
""".strip()


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return {}
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
