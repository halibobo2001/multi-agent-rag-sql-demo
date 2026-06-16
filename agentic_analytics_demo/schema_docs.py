from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SchemaDocument:
    doc_id: str
    title: str
    text: str


SCHEMA_DOCUMENTS = [
    SchemaDocument(
        "events",
        "events 电商行为事件表",
        "events(timestamp, event_time, visitorid, event, itemid, transactionid)。"
        "每行是 Retailrocket 用户行为事件。event 只有 view、addtocart、transaction。"
        "visitorid 是匿名访客，itemid 是商品，transactionid 只在 transaction 事件中有值。"
    ),
    SchemaDocument(
        "category_tree",
        "category_tree 品类树",
        "category_tree(categoryid, parentid)。categoryid 是商品品类，parentid 是上级品类；"
        "parentid 为空代表顶层品类。可用于品类层级聚合。"
    ),
    SchemaDocument(
        "item_category_history",
        "item_category_history 商品品类历史",
        "item_category_history(timestamp, event_time, itemid, categoryid)。"
        "来自 item_properties 中 property='categoryid' 的记录。用于分析商品所属品类随时间变化。"
    ),
    SchemaDocument(
        "item_latest_category",
        "item_latest_category 商品最新品类",
        "item_latest_category(itemid, categoryid, observed_at)。每个商品一行，是最新可见 categoryid。"
        "常见 join：events e LEFT JOIN item_latest_category ic ON e.itemid = ic.itemid。"
    ),
    SchemaDocument(
        "item_availability_history",
        "item_availability_history 商品可售状态历史",
        "item_availability_history(timestamp, event_time, itemid, available)。"
        "来自 item_properties 中 property='available' 的记录，available 通常为 0/1。"
    ),
    SchemaDocument(
        "item_latest_availability",
        "item_latest_availability 商品最新可售状态",
        "item_latest_availability(itemid, available, observed_at)。每个商品一行，用于过滤当前可售商品。"
    ),
    SchemaDocument(
        "metric_funnel",
        "指标：电商漏斗",
        "浏览量 views = SUM(event='view')；加购量 add_to_carts = SUM(event='addtocart')；"
        "交易量 transactions = SUM(event='transaction')。加购率 = addtocart / view；购买率 = transaction / view。"
        "注意 transaction 事件可能没有成对 addtocart，因此默认品类转化率优先使用 transaction / view。"
    ),
    SchemaDocument(
        "metric_visitors",
        "指标：访客与商品热度",
        "独立访客数使用 COUNT(DISTINCT visitorid)。商品热度可用浏览量、加购量、交易量和独立访客数综合判断。"
        "高浏览低购买商品通常是 views 高但 transactions 或 transaction/view 低。"
    ),
    SchemaDocument(
        "metric_category",
        "指标：品类分析",
        "按品类分析时使用 item_latest_category 连接 events。"
        "示例：events e LEFT JOIN item_latest_category ic ON e.itemid = ic.itemid GROUP BY ic.categoryid。"
    ),
    SchemaDocument(
        "metric_time",
        "时间字段规则",
        "所有行为时间过滤优先使用 events.event_time。属性历史使用 item_category_history.event_time 或 item_availability_history.event_time。"
        "Retailrocket 原始时间戳是毫秒，SQLite 仓库已转成 event_time 文本。"
        "数据大致覆盖 2015 年 5 月到 2015 年 9 月；不要使用 date('now') 过滤该历史数据。"
    ),
    SchemaDocument(
        "sql_examples",
        "常见 SQL 模式",
        "商品热度：FROM events WHERE event='view' GROUP BY itemid。"
        "品类转化：events e LEFT JOIN item_latest_category ic ON e.itemid=ic.itemid，然后按 categoryid 聚合 view/addtocart/transaction。"
        "漏斗趋势：SELECT DATE(event_time), event, COUNT(*) FROM events GROUP BY DATE(event_time), event。"
    ),
]
