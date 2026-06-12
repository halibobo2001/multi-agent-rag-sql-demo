# Multi-Agent RAG SQL Analytics Demo

一个本地可运行的中文数据分析 Demo：自然语言问题 -> Schema RAG -> SQL 生成 -> 安全校验 -> SQLite 查询 -> 数据分析 -> Plotly 可视化。

## 快速开始

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env，填入 GEMINI_API_KEY
streamlit run app.py
```

如果没有配置 `GEMINI_API_KEY`，系统会自动使用内置 fallback 规则，仍可跑通示例问题；配置后会调用 Gemini API。默认模型为 `gemini-2.5-flash`。
也可以把单行 Gemini key 放在项目根目录的 `key.txt`，应用会在 `.env`/环境变量不存在时自动读取。

## 示例问题

- 本月哪些国家转化率最高？
- 比较移动端和桌面端在漏斗中的流失情况。
- 找出德国用户最常访问的功能页面。
- A/B 实验不同 variant 的收入表现如何？
- 各国家过去 30 天的活跃会话趋势如何？

## 项目结构

- `app.py`：Streamlit 本地 Web 应用入口。
- `agentic_analytics_demo/`：数据、RAG、LLM、SQL 安全、多 Agent 和可视化模块。
- `tests/`：核心单元测试和 fake LLM 集成测试。
- `data/`：运行时自动生成 SQLite 数据库和 ChromaDB 索引。

## 测试

```powershell
pytest
```
