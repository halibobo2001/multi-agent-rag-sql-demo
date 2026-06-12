from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from agentic_analytics_demo.agents import AnalyticsAgentSystem
from agentic_analytics_demo.config import AppConfig, load_environment
from agentic_analytics_demo.llm import GeminiClient
from agentic_analytics_demo.rag import SchemaRAG
from agentic_analytics_demo.viz import render_plotly_chart
from agentic_analytics_demo.warehouse import ensure_demo_warehouse


EXAMPLES = [
    "本月哪些国家转化率最高？",
    "比较移动端和桌面端在漏斗中的流失情况。",
    "找出德国用户最常访问的功能页面。",
    "A/B 实验不同 variant 的收入表现如何？",
    "各国家过去 30 天的活跃会话趋势如何？",
]


@st.cache_resource(show_spinner=False)
def bootstrap() -> tuple[AppConfig, AnalyticsAgentSystem]:
    load_environment()
    config = AppConfig.from_env()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    ensure_demo_warehouse(config.db_path)
    rag = SchemaRAG(config.chroma_dir)
    rag.ensure_index()
    llm = GeminiClient(api_key=config.gemini_api_key, model=config.gemini_model)
    return config, AnalyticsAgentSystem(config.db_path, rag, llm)


def run_question(system: AnalyticsAgentSystem, question: str) -> None:
    with st.spinner("Agent 正在检索 Schema、生成 SQL 并分析结果..."):
        result = system.run(question)
    st.session_state["last_result"] = result


def main() -> None:
    st.set_page_config(page_title="Multi-Agent RAG SQL Demo", layout="wide")
    config, system = bootstrap()

    st.title("Multi-Agent RAG SQL 数据分析 Demo")
    st.caption("跨国用户行为日志分析 | Gemini + LangGraph + ChromaDB + SQLite + Plotly")

    with st.sidebar:
        st.subheader("运行状态")
        st.write(f"数据库: `{config.db_path.name}`")
        st.write(f"模型: `{config.gemini_model}`")
        if config.gemini_api_key:
            st.write(f"Gemini API: 已配置（{config.gemini_key_source}）")
            st.write("调用模式: `Live Gemini`")
        else:
            st.write("Gemini API: 未配置")
            st.write("调用模式: `fallback`")
        st.write(f"RAG: `{system.rag.backend}`")
        st.divider()
        st.subheader("示例问题")
        for index, example in enumerate(EXAMPLES):
            if st.button(example, key=f"example_{index}", use_container_width=True):
                st.session_state["question"] = example
                run_question(system, example)

    question = st.text_area(
        "输入业务问题",
        value=st.session_state.get("question", EXAMPLES[0]),
        height=92,
        placeholder="例如：本月哪些国家转化率最高？",
    )
    cols = st.columns([1, 4])
    with cols[0]:
        submitted = st.button("运行分析", type="primary", use_container_width=True)
    if submitted and question.strip():
        st.session_state["question"] = question.strip()
        run_question(system, question.strip())

    result = st.session_state.get("last_result")
    if not result:
        st.info("选择一个示例问题或输入自己的业务问题开始分析。")
        return

    if result.error:
        st.error(result.error)

    trace_col, sql_col = st.columns([1, 1])
    with trace_col:
        st.subheader("Agent 执行轨迹")
        for item in result.trace:
            st.write(f"- {item}")
    with sql_col:
        st.subheader("生成 SQL")
        st.code(result.sql or "-- 当前请求未生成 SQL", language="sql")

    with st.expander("RAG 检索到的 Schema / 指标上下文", expanded=False):
        for context in result.contexts:
            st.markdown(f"**{context.title}**")
            st.write(context.text)

    if isinstance(result.dataframe, pd.DataFrame) and not result.dataframe.empty:
        chart_col, table_col = st.columns([1.1, 1])
        with chart_col:
            st.subheader("可视化")
            fig = render_plotly_chart(result.dataframe, result.chart_spec)
            st.plotly_chart(fig, use_container_width=True)
        with table_col:
            st.subheader("查询结果")
            st.dataframe(result.dataframe, use_container_width=True, hide_index=True)
    elif isinstance(result.dataframe, pd.DataFrame):
        st.warning("查询执行成功，但没有返回数据。")

    st.subheader("中文分析结论")
    st.write(result.analysis or "暂无分析结论。")


if __name__ == "__main__":
    main()
