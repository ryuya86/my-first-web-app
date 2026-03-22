"""
受注率ダッシュボード — 週次・月次レポートをSlackに自動投稿
"""

from datetime import datetime, timedelta
from history_db import (
    get_conversion_stats,
    get_category_stats,
    get_response_time_stats,
    generate_monthly_summary,
)


def build_weekly_report_blocks():
    """週次レポートのSlackブロックを生成"""
    stats = get_conversion_stats(days=7)
    category_stats = get_category_stats(days=7)
    response_stats = get_response_time_stats(days=7)
    prev_stats = get_conversion_stats(days=14)  # 前週比較用

    # 変換率計算
    applied = stats.get("total_applied", 0) or 0
    responded = stats.get("total_responded", 0) or 0
    contracted = stats.get("total_contracted", 0) or 0
    completed = stats.get("total_completed", 0) or 0
    revenue = stats.get("total_revenue", 0) or 0

    response_rate = (responded / applied * 100) if applied > 0 else 0
    contract_rate = (contracted / applied * 100) if applied > 0 else 0

    # 前週比
    prev_applied = prev_stats.get("total_applied", 0) or 0
    prev_contracted = prev_stats.get("total_contracted", 0) or 0
    prev_contract_rate = (prev_contracted / prev_applied * 100) if prev_applied > 0 else 0

    rate_diff = contract_rate - prev_contract_rate
    rate_arrow = "📈" if rate_diff > 0 else ("📉" if rate_diff < 0 else "➡️")

    today = datetime.now()
    week_start = (today - timedelta(days=7)).strftime("%m/%d")
    week_end = today.strftime("%m/%d")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"📊 週次レポート ({week_start}〜{week_end})"},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*🎯 ファネル概要*\n"
                    f"```\n"
                    f"応募数:   {applied}件\n"
                    f"返信あり: {responded}件 ({response_rate:.1f}%)\n"
                    f"受注:     {contracted}件 ({contract_rate:.1f}%)\n"
                    f"完了:     {completed}件\n"
                    f"売上:     ¥{revenue:,}\n"
                    f"```\n"
                    f"{rate_arrow} 受注率前週比: {rate_diff:+.1f}pt"
                ),
            },
        },
    ]

    # カテゴリ別
    if category_stats:
        cat_lines = ["*📂 カテゴリ別実績*\n"]
        for cs in category_stats[:5]:
            cat = cs.get("category", "不明") or "不明"
            cat_applied = cs.get("applied", 0)
            cat_contracted = cs.get("contracted", 0)
            cat_revenue = cs.get("revenue", 0) or 0
            cat_rate = (cat_contracted / cat_applied * 100) if cat_applied > 0 else 0
            bar = "█" * int(cat_rate / 10) + "░" * (10 - int(cat_rate / 10))
            cat_lines.append(
                f"`{bar}` *{cat}*: {cat_contracted}/{cat_applied}件 "
                f"({cat_rate:.0f}%) ¥{cat_revenue:,}"
            )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(cat_lines)},
        })

    # 返信速度
    if response_stats.get("total_messages"):
        avg_time = response_stats.get("avg_response_time", 0) or 0
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*⏱️ 返信速度*\n"
                    f"平均: {avg_time:.0f}分 | "
                    f"最速: {response_stats.get('min_response_time', 0)}分 | "
                    f"最遅: {response_stats.get('max_response_time', 0)}分"
                ),
            },
        })

    # マッチングスコア
    avg_score = stats.get("avg_match_score") or 0
    if avg_score > 0:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🎯 平均マッチングスコア:* {avg_score:.0f}点",
            },
        })

    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"生成日時: {today.strftime('%Y-%m-%d %H:%M')}"},
        ],
    })

    return blocks


def build_monthly_report_blocks(year_month=None):
    """月次収益レポートのSlackブロックを生成"""
    data = generate_monthly_summary(year_month)

    if not year_month:
        year_month = datetime.now().strftime("%Y-%m")

    applications = data.get("total_applications", 0)
    contracts = data.get("total_contracts", 0)
    completed = data.get("total_completed", 0)
    revenue = data.get("total_revenue", 0)
    hours = data.get("total_hours", 0)
    hourly_rate = data.get("avg_hourly_rate", 0)

    contract_rate = (contracts / applications * 100) if applications > 0 else 0

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"💰 月次収益レポート ({year_month})"},
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*📊 サマリー*\n"
                    f"```\n"
                    f"応募数:     {applications}件\n"
                    f"受注数:     {contracts}件 (受注率: {contract_rate:.1f}%)\n"
                    f"完了数:     {completed}件\n"
                    f"売上合計:   ¥{revenue:,}\n"
                    f"稼働時間:   {hours:.1f}h\n"
                    f"時給換算:   ¥{hourly_rate:,.0f}/h\n"
                    f"```"
                ),
            },
        },
    ]

    # カテゴリ別の月次集計
    category_stats = get_category_stats(days=31)
    if category_stats:
        cat_lines = ["*📂 カテゴリ別売上*\n"]
        for cs in category_stats:
            cat = cs.get("category", "不明") or "不明"
            cat_revenue = cs.get("revenue", 0) or 0
            cat_contracted = cs.get("contracted", 0)
            pct = (cat_revenue / revenue * 100) if revenue > 0 else 0
            cat_lines.append(f"• *{cat}*: ¥{cat_revenue:,} ({pct:.0f}%) — {cat_contracted}件")
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(cat_lines)},
        })

    # P/L概要
    system_fee_rate = 0.20  # CrowdWorks手数料（概算20%）
    gross = revenue
    fee = int(revenue * system_fee_rate)
    net = gross - fee

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                f"*💵 P/L概要*\n"
                f"```\n"
                f"売上総額:     ¥{gross:,}\n"
                f"手数料(20%):  -¥{fee:,}\n"
                f"─────────────────\n"
                f"手取り:       ¥{net:,}\n"
                f"```"
            ),
        },
    })

    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M')}"},
        ],
    })

    return blocks


def send_weekly_report(slack_client, channel):
    """週次レポートをSlackに送信"""
    blocks = build_weekly_report_blocks()
    slack_client.chat_postMessage(
        channel=channel,
        blocks=blocks,
        text="📊 週次レポート",
    )


def send_monthly_report(slack_client, channel, year_month=None):
    """月次収益レポートをSlackに送信"""
    blocks = build_monthly_report_blocks(year_month)
    slack_client.chat_postMessage(
        channel=channel,
        blocks=blocks,
        text="💰 月次収益レポート",
    )


if __name__ == "__main__":
    blocks = build_weekly_report_blocks()
    for b in blocks:
        if b.get("type") == "section":
            print(b["text"]["text"])
