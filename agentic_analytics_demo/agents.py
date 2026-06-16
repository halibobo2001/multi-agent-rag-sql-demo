from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict

import pandas as pd

from .llm import GeminiClient, SQLGeneration
from .rag import RetrievedContext, SchemaRAG
from .sql_guard import validate_sql
from .viz import normalize_chart_spec


class AgentState(TypedDict, total=False):
    question: str
    route: str
    contexts: list[RetrievedContext]
    generation: SQLGeneration
    sql: str
    chart_spec: dict[str, Any]
    dataframe: pd.DataFrame
    analysis: str
    trace: list[str]
    error: str
    previous_error: str


@dataclass
class AgentRunResult:
    question: str
    route: str = "analytics"
    contexts: list[RetrievedContext] = field(default_factory=list)
    sql: str = ""
    chart_spec: dict[str, Any] = field(default_factory=dict)
    dataframe: pd.DataFrame = field(default_factory=pd.DataFrame)
    analysis: str = ""
    trace: list[str] = field(default_factory=list)
    error: str = ""


class AnalyticsAgentSystem:
    def __init__(self, db_path: Path, rag: SchemaRAG, llm: GeminiClient):
        self.db_path = db_path
        self.rag = rag
        self.llm = llm

    def run(self, question: str) -> AgentRunResult:
        state: AgentState = {"question": question, "trace": []}
        attempts = 0
        while attempts < 2:
            state = self._run_graph_once(state)
            if not state.get("error") or state.get("dataframe") is not None:
                break
            state["previous_error"] = state["error"]
            state["trace"].append("Repair Loop: 将错误反馈给 SQL Generator 再试一次")
            attempts += 1
        return AgentRunResult(
            question=question,
            route=state.get("route", "analytics"),
            contexts=state.get("contexts", []),
            sql=state.get("sql", ""),
            chart_spec=state.get("chart_spec", {}),
            dataframe=state.get("dataframe", pd.DataFrame()),
            analysis=state.get("analysis", ""),
            trace=state.get("trace", []),
            error=state.get("error", ""),
        )

    def _run_graph_once(self, state: AgentState) -> AgentState:
        try:
            from langgraph.graph import END, StateGraph

            graph = StateGraph(AgentState)
            graph.add_node("semantic_router", self._semantic_router)
            graph.add_node("schema_retriever", self._schema_retriever)
            graph.add_node("sql_generator", self._sql_generator)
            graph.add_node("sql_validator", self._sql_validator)
            graph.add_node("query_executor", self._query_executor)
            graph.add_node("analyst", self._analyst)
            graph.add_node("visualization", self._visualization)
            graph.set_entry_point("semantic_router")
            graph.add_edge("semantic_router", "schema_retriever")
            graph.add_edge("schema_retriever", "sql_generator")
            graph.add_edge("sql_generator", "sql_validator")
            graph.add_edge("sql_validator", "query_executor")
            graph.add_edge("query_executor", "analyst")
            graph.add_edge("analyst", "visualization")
            graph.add_edge("visualization", END)
            return graph.compile().invoke(state)
        except Exception:
            for node in [
                self._semantic_router,
                self._schema_retriever,
                self._sql_generator,
                self._sql_validator,
                self._query_executor,
                self._analyst,
                self._visualization,
            ]:
                state.update(node(state))
            return state

    def _semantic_router(self, state: AgentState) -> AgentState:
        question = state["question"].strip()
        route = "analytics"
        if any(word in question for word in ["表结构", "schema", "字段", "有哪些表"]):
            route = "schema_help"
        if any(word in question for word in ["写邮件", "翻译", "天气", "代码审查"]):
            route = "unsupported"
        return _merge(state, route=route, trace_item=f"Semantic Router: route={route}")

    def _schema_retriever(self, state: AgentState) -> AgentState:
        contexts = self.rag.retrieve(state["question"], top_k=5)
        return _merge(
            state,
            contexts=contexts,
            trace_item=f"Schema Retriever: 返回 {len(contexts)} 条上下文，backend={self.rag.backend}",
        )

    def _sql_generator(self, state: AgentState) -> AgentState:
        if state.get("route") == "unsupported":
            return _merge(state, error="这个 demo 只处理数据分析和 Schema 相关问题。", trace_item="SQL Generator: 跳过")
        if state.get("route") == "schema_help":
            context_text = "\n\n".join(ctx.text for ctx in state.get("contexts", []))
            return _merge(
                state,
                analysis=f"相关 Schema 信息：\n{context_text}",
                trace_item="SQL Generator: Schema help 请求无需生成 SQL",
            )
        generation = self.llm.generate_sql(
            state["question"],
            state.get("contexts", []),
            previous_error=state.get("previous_error"),
        )
        provider_label = "GVMZ" if getattr(self.llm, "provider", "") == "gvmz" else "Gemini"
        return _merge(
            state,
            generation=generation,
            sql=generation.sql,
            chart_spec=generation.chart_spec,
            trace_item=f"SQL Generator: 生成 SQL ({provider_label if self.llm.is_live else 'fallback'})",
        )

    def _sql_validator(self, state: AgentState) -> AgentState:
        if not state.get("sql"):
            return state
        validation = validate_sql(state["sql"], self.db_path)
        if validation.ok:
            return _merge(state, sql=validation.sql, error="", trace_item="SQL Validator: 通过只读安全校验")
        return _merge(state, sql=validation.sql, error=validation.error, trace_item=f"SQL Validator: 拦截 - {validation.error}")

    def _query_executor(self, state: AgentState) -> AgentState:
        if state.get("error") or not state.get("sql"):
            return state
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            dataframe = pd.read_sql_query(state["sql"], conn)
        except Exception as exc:
            return _merge(state, error=f"SQL 执行失败: {exc}", trace_item=f"Query Executor: 失败 - {exc}")
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return _merge(state, dataframe=dataframe, trace_item=f"Query Executor: 返回 {len(dataframe)} 行")

    def _analyst(self, state: AgentState) -> AgentState:
        dataframe = state.get("dataframe")
        if dataframe is None:
            return state
        analysis = self.llm.analyze(state["question"], state.get("sql", ""), dataframe)
        return _merge(state, analysis=analysis, trace_item="Analyst Agent: 生成中文洞察")

    def _visualization(self, state: AgentState) -> AgentState:
        dataframe = state.get("dataframe")
        if dataframe is None:
            return state
        chart_spec = normalize_chart_spec(dataframe, state.get("chart_spec"))
        return _merge(state, chart_spec=chart_spec, trace_item=f"Visualization Agent: chart={chart_spec.get('type')}")


def _merge(state: AgentState, trace_item: str | None = None, **updates: Any) -> AgentState:
    next_state = dict(state)
    next_state.update(updates)
    if trace_item:
        trace = list(next_state.get("trace", []))
        trace.append(trace_item)
        next_state["trace"] = trace
    return next_state
