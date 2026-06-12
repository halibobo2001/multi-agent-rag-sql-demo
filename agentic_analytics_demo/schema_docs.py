from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaDocument:
    doc_id: str
    title: str
    text: str


SCHEMA_DOCUMENTS = [
    SchemaDocument(
        "users",
        "users 用户主表",
        "users(user_id, country, language, signup_date, acquisition_channel, account_tier)。"
        "每行代表一个注册用户。country 可用于跨国分析；account_tier 包含 free、pro、enterprise。",
    ),
    SchemaDocument(
        "sessions",
        "sessions 访问会话表",
        "sessions(session_id, user_id, device_type, browser, session_country, started_at, duration_seconds)。"
        "与 users 通过 user_id 关联。device_type 包含 mobile、desktop、tablet。",
    ),
    SchemaDocument(
        "events",
        "events 用户行为事件表",
        "events(event_id, session_id, event_type, page, feature, occurred_at)。"
        "与 sessions 通过 session_id 关联。用于页面访问、功能使用、漏斗步骤和活跃行为分析。",
    ),
    SchemaDocument(
        "conversions",
        "conversions 转化漏斗表",
        "conversions(conversion_id, session_id, user_id, funnel_step, converted, revenue, occurred_at)。"
        "funnel_step 包含 view_product、start_trial、checkout、paid。converted 为 0/1，revenue 为收入。",
    ),
    SchemaDocument(
        "experiments",
        "experiments A/B 实验曝光表",
        "experiments(experiment_id, user_id, experiment_name, variant, exposed_at)。"
        "与 users/conversions 通过 user_id 关联，可分析不同 variant 的转化率和收入。",
    ),
    SchemaDocument(
        "metric_conversion_rate",
        "指标：转化率",
        "转化率通常计算为 AVG(converted) 或 SUM(converted) / COUNT(*)，来自 conversions 表。"
        "按国家分析时 join users；按设备分析时 join sessions。"
        "按月份、最近、本月过滤转化数据时使用 conversions.occurred_at，不要使用 users.signup_date。",
    ),
    SchemaDocument(
        "metric_revenue",
        "指标：收入表现",
        "收入使用 SUM(revenue)、AVG(revenue) 或 revenue per user。实验收入分析需要 experiments join conversions。",
    ),
    SchemaDocument(
        "metric_activity",
        "指标：活跃度",
        "活跃度可使用 COUNT(DISTINCT session_id)、COUNT(*) events 或 COUNT(DISTINCT user_id)。"
        "时间趋势通常使用 DATE(started_at) 或 DATE(occurred_at)。",
    ),
    SchemaDocument(
        "metric_time_fields",
        "时间字段选择规则",
        "用户注册分析使用 users.signup_date；会话活跃分析使用 sessions.started_at；"
        "事件/功能访问分析使用 events.occurred_at；转化率、漏斗和收入分析使用 conversions.occurred_at；"
        "A/B 实验曝光分析使用 experiments.exposed_at。除非用户明确问注册，否则不要用 signup_date 过滤业务结果。",
    ),
    SchemaDocument(
        "join_examples",
        "常见 Join",
        "国家转化：users u JOIN conversions c ON u.user_id = c.user_id。"
        "设备漏斗：sessions s JOIN conversions c ON s.session_id = c.session_id。"
        "功能访问：sessions s JOIN users u ON s.user_id = u.user_id JOIN events e ON s.session_id = e.session_id。",
    ),
]
