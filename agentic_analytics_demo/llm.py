from __future__ import annotations

import json
import os
import re
import time
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
    def __init__(
        self,
        api_key: str | None = None,
        model: str = "gemini-2.5-flash",
        provider: str = "gemini",
        base_url: str = "https://gvmz.systems/v1",
    ):
        self.api_key = (api_key or os.getenv("GEMINI_API_KEY", "")).strip()
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self._client = None
        if self.api_key and self.provider == "gemini":
            try:
                from google import genai

                self._client = genai.Client(api_key=self.api_key)
            except Exception:
                self._client = None

    @property
    def is_live(self) -> bool:
        if self.provider == "gvmz":
            return bool(self.api_key)
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
        try:
            text = self._generate_text(prompt)
        except Exception:
            return fallback_sql_generation(question)
        payload = _extract_json(text)
        if not payload.get("sql"):
            return fallback_sql_generation(question)
        return SQLGeneration(
            sql=str(payload["sql"]),
            chart_spec=payload.get("chart_spec") or {"type": "bar", "title": "分析结果"},
            rationale=str(payload.get("rationale", "Gemini generated SQL.")),
        )

    def analyze(self, question: str, sql: str, dataframe: pd.DataFrame) -> str:
        if dataframe.empty:
            return "查询成功，但没有返回符合条件的数据。可以尝试放宽筛选条件，或先查看整体分布。"
        if not self.is_live:
            return fallback_analysis(question, dataframe)

        preview = dataframe.head(20).to_markdown(index=False)
        prompt = (
            "你是电商推荐系统数据分析 Agent。请用中文给出 3-5 句简洁业务洞察，"
            "指出商品/品类机会、漏斗异常和推荐优化动作。\n"
            f"用户问题: {question}\nSQL:\n{sql}\n结果预览:\n{preview}\n"
        )
        try:
            return self._generate_text(prompt).strip() or fallback_analysis(question, dataframe)
        except Exception:
            return fallback_analysis(question, dataframe)

    def _generate_text(self, prompt: str) -> str:
        if self.provider == "gvmz":
            return self._generate_text_with_gvmz(prompt)
        response = self._client.models.generate_content(model=self.model, contents=prompt)
        return getattr(response, "text", "")

    def _generate_text_with_gvmz(self, prompt: str) -> str:
        import httpx

        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a precise data assistant. Follow the user's output format exactly.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
            timeout=90,
        )
        if response.status_code in {429, 500, 502, 503, 504}:
            time.sleep(1.5)
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a precise data assistant. Follow the user's output format exactly.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                },
                timeout=90,
            )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]


def fallback_sql_generation(question: str) -> SQLGeneration:
    normalized = question.lower()
    if any(word in question for word in ["品类", "类目", "category", "转化", "转化率"]) or "conversion" in normalized:
        return SQLGeneration(
            sql="""
            SELECT
                COALESCE(CAST(ic.categoryid AS TEXT), 'unknown') AS categoryid,
                SUM(CASE WHEN e.event = 'view' THEN 1 ELSE 0 END) AS views,
                SUM(CASE WHEN e.event = 'addtocart' THEN 1 ELSE 0 END) AS add_to_carts,
                SUM(CASE WHEN e.event = 'transaction' THEN 1 ELSE 0 END) AS transactions,
                ROUND(
                    100.0 * SUM(CASE WHEN e.event = 'transaction' THEN 1 ELSE 0 END)
                    / NULLIF(SUM(CASE WHEN e.event = 'view' THEN 1 ELSE 0 END), 0),
                    2
                ) AS purchase_rate_pct
            FROM events e
            LEFT JOIN item_latest_category ic ON e.itemid = ic.itemid
            GROUP BY ic.categoryid
            HAVING views >= 100
            ORDER BY purchase_rate_pct DESC
            """,
            chart_spec={
                "type": "bar",
                "x": "categoryid",
                "y": "purchase_rate_pct",
                "title": "品类购买转化率",
            },
            rationale="Fallback matched category funnel conversion analysis.",
        )
    if any(word in question for word in ["趋势", "按天", "日期", "漏斗", "trend"]):
        return SQLGeneration(
            sql="""
            SELECT
                DATE(event_time) AS event_date,
                event,
                COUNT(*) AS event_count,
                COUNT(DISTINCT visitorid) AS unique_visitors
            FROM events
            GROUP BY DATE(event_time), event
            ORDER BY event_date, event
            """,
            chart_spec={
                "type": "line",
                "x": "event_date",
                "y": "event_count",
                "color": "event",
                "title": "电商行为漏斗趋势",
            },
            rationale="Fallback matched daily funnel trend.",
        )
    if any(word in question for word in ["高浏览", "低购买", "推荐", "优化", "popular"]):
        return SQLGeneration(
            sql="""
            SELECT
                e.itemid,
                COALESCE(CAST(ic.categoryid AS TEXT), 'unknown') AS categoryid,
                SUM(CASE WHEN e.event = 'view' THEN 1 ELSE 0 END) AS views,
                SUM(CASE WHEN e.event = 'addtocart' THEN 1 ELSE 0 END) AS add_to_carts,
                SUM(CASE WHEN e.event = 'transaction' THEN 1 ELSE 0 END) AS transactions,
                ROUND(
                    100.0 * SUM(CASE WHEN e.event = 'transaction' THEN 1 ELSE 0 END)
                    / NULLIF(SUM(CASE WHEN e.event = 'view' THEN 1 ELSE 0 END), 0),
                    3
                ) AS purchase_rate_pct
            FROM events e
            LEFT JOIN item_latest_category ic ON e.itemid = ic.itemid
            GROUP BY e.itemid, ic.categoryid
            HAVING views >= 20
            ORDER BY purchase_rate_pct ASC, views DESC
            """,
            chart_spec={
                "type": "bar",
                "x": "itemid",
                "y": "views",
                "color": "categoryid",
                "title": "高浏览低购买商品",
            },
            rationale="Fallback matched recommendation optimization candidates.",
        )
    if any(word in question for word in ["访客", "visitor", "交易访客", "购买用户"]):
        return SQLGeneration(
            sql="""
            SELECT
                COALESCE(CAST(ic.categoryid AS TEXT), 'unknown') AS categoryid,
                COUNT(DISTINCT e.visitorid) AS unique_visitors,
                COUNT(DISTINCT CASE WHEN e.event = 'transaction' THEN e.visitorid END) AS purchasing_visitors,
                SUM(CASE WHEN e.event = 'transaction' THEN 1 ELSE 0 END) AS transactions
            FROM events e
            LEFT JOIN item_latest_category ic ON e.itemid = ic.itemid
            GROUP BY ic.categoryid
            ORDER BY purchasing_visitors DESC, transactions DESC
            """,
            chart_spec={
                "type": "bar",
                "x": "categoryid",
                "y": "purchasing_visitors",
                "title": "品类交易访客数",
            },
            rationale="Fallback matched category purchasing visitor analysis.",
        )
    return SQLGeneration(
        sql="""
        SELECT
            e.itemid,
            COALESCE(CAST(ic.categoryid AS TEXT), 'unknown') AS categoryid,
            COUNT(*) AS views,
            COUNT(DISTINCT e.visitorid) AS unique_viewers
        FROM events e
        LEFT JOIN item_latest_category ic ON e.itemid = ic.itemid
        WHERE e.event = 'view'
        GROUP BY e.itemid, ic.categoryid
        ORDER BY views DESC
        """,
        chart_spec={"type": "bar", "x": "itemid", "y": "views", "color": "categoryid", "title": "商品浏览量排行"},
        rationale="Fallback defaulted to top viewed items.",
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
    lines.append("这是 fallback 分析；配置 GEMINI_API_KEY 后会生成更自然的推荐系统业务洞察。")
    return " ".join(lines)


def _build_sql_prompt(question: str, contexts: list[RetrievedContext], previous_error: str | None) -> str:
    context_text = "\n\n".join(f"{ctx.title}\n{ctx.text}" for ctx in contexts)
    repair_text = f"\n上一次 SQL 错误: {previous_error}\n请修复。" if previous_error else ""
    return f"""
你是只读 SQLite 电商推荐系统数据分析 SQL Agent。必须只输出 JSON，不要 Markdown。
目标：把用户中文问题转换为安全 SQLite SQL，并给出 Plotly 图表规格。

硬性规则：
1. 只能生成 SELECT 或 WITH 查询。
2. 禁止 INSERT/UPDATE/DELETE/DROP/ALTER/ATTACH/PRAGMA/CREATE。
3. 只能使用给定 Schema 中存在的表和字段。
4. SQL 不要包含注释。
5. 图表规格只允许 type/x/y/color/title 字段，type 为 bar/line/scatter/pie/table 之一。
6. 时间过滤必须使用 events.event_time；Retailrocket 是 2015 年历史数据，不要使用 date('now')。
7. 漏斗事件固定为 view、addtocart、transaction；不要编造 revenue、country、user、session、experiment 等字段。

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
