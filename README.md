# Multi-Agent RAG SQL Analytics Demo

一个基于 Retailrocket recommender system dataset 的本地中文数据分析 Demo：自然语言问题 -> Schema RAG -> SQL 生成 -> 安全校验 -> SQLite 查询 -> 数据分析 -> Plotly 可视化。

## 快速开始

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env，填入 GEMINI_API_KEY
streamlit run app.py
```

请把 Kaggle 数据文件放在项目根目录的 `dataset/` 目录下：

- `events.csv`
- `item_properties_part1.csv`
- `item_properties_part2.csv`
- `category_tree.csv`

首次启动会自动构建 `data/retailrocket.sqlite`。原始 Kaggle CSV 和生成的 SQLite 数据库都不会被提交到 Git。

如果没有配置 `GEMINI_API_KEY`，系统会自动使用内置 fallback 规则，仍可跑通示例问题；配置后会调用 Gemini API。默认模型为 `gemini-2.5-flash`。
也可以把单行 Gemini key 放在项目根目录的 `key.txt`，应用会在 `.env`/环境变量不存在时自动读取。

如果根目录存在 `key2.txt`，系统会优先使用鬼魅云 GhostCloud 的 OpenAI 兼容中转：

- BaseURL: `https://gvmz.systems/v1`
- 默认模型: `gemini-3-flash-preview`
- Key 文件: `key2.txt`

也可以在 `.env` 里用 `LLM_PROVIDER`、`GVMZ_API_KEY`、`GVMZ_MODEL`、`GVMZ_BASE_URL` 覆盖。

## 示例问题

- 哪些商品浏览量最高？
- 哪些品类的购买转化率最高？
- 按天展示 view、addtocart、transaction 的漏斗趋势。
- 找出高浏览但低购买的商品，适合做推荐优化。
- 哪些品类贡献了最多交易访客？

## 项目结构

- `app.py`：Streamlit 本地 Web 应用入口。
- `agentic_analytics_demo/`：Retailrocket 数据导入、RAG、LLM、SQL 安全、多 Agent 和可视化模块。
- `tests/`：核心单元测试和 fake LLM 集成测试。
- `data/`：运行时自动生成 SQLite 数据库和 ChromaDB 索引。

## 测试

```powershell
pytest
```

## 教学 Notebook

面向 AI 小白的半天工作坊教程位于：

```text
tutorials/retailrocket_agent_tutorial.ipynb
```

Notebook 默认使用离线 fallback 跑通完整 Agent 链路，不消耗 GVMZ/Gemini API 额度。
