"""
返信遅延アラート — 未返信メッセージの検出・エスカレーション通知
"""

import os
from datetime import datetime, timedelta
from history_db import get_pending_replies, get_db

ALERT_THRESHOLD_HOURS = int(os.environ.get("CW_REPLY_ALERT_HOURS", "2"))
ESCALATION_THRESHOLD_HOURS = int(os.environ.get("CW_REPLY_ESCALATION_HOURS", "6"))


def check_delayed_replies():
    """遅延している返信を検出"""
    alerts = []
    escalations = []

    # 通常アラート（2時間以上）
    pending = get_pending_replies(hours=ALERT_THRESHOLD_HOURS)
    for msg in pending:
        created = datetime.fromisoformat(msg["created_at"])
        elapsed = datetime.now() - created
        hours = elapsed.total_seconds() / 3600

        entry = {
            "thread_id": msg["thread_id"],
            "thread_url": msg["thread_url"],
            "client_name": msg["client_name"],
            "job_title": msg.get("job_title", "不明"),
            "body_preview": msg["body"][:100],
            "elapsed_hours": round(hours, 1),
            "created_at": msg["created_at"],
        }

        if hours >= ESCALATION_THRESHOLD_HOURS:
            escalations.append(entry)
        else:
            alerts.append(entry)

    return {"alerts": alerts, "escalations": escalations}


def build_alert_blocks(result):
    """Slack通知用ブロックを生成"""
    alerts = result["alerts"]
    escalations = result["escalations"]

    if not alerts and not escalations:
        return None

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "⏰ 返信遅延アラート" if not escalations else "🚨 返信遅延エスカレーション",
            },
        },
    ]

    if escalations:
        lines = ["*🚨 緊急（6時間以上未返信）:*\n"]
        for e in escalations:
            lines.append(
                f"• *{e['client_name']}* ({e['job_title'][:30]})\n"
                f"  _{e['elapsed_hours']}時間経過_ | "
                f"<{e['thread_url']}|CrowdWorksで開く>\n"
                f"  > {e['body_preview']}"
            )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        })

    if alerts:
        lines = ["*⏰ 注意（2時間以上未返信）:*\n"]
        for a in alerts:
            lines.append(
                f"• *{a['client_name']}* ({a['job_title'][:30]}) — "
                f"_{a['elapsed_hours']}時間経過_ "
                f"<{a['thread_url']}|開く>"
            )
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        })

    total = len(alerts) + len(escalations)
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"未返信合計: {total}件 | 確認時刻: {datetime.now().strftime('%H:%M')}"},
        ],
    })

    return blocks


def send_delay_alerts(slack_client, channel):
    """遅延アラートをSlackに送信"""
    result = check_delayed_replies()
    blocks = build_alert_blocks(result)

    if not blocks:
        return False

    text = "🚨 返信遅延エスカレーション" if result["escalations"] else "⏰ 返信遅延アラート"
    slack_client.chat_postMessage(
        channel=channel,
        blocks=blocks,
        text=text,
    )
    return True


if __name__ == "__main__":
    result = check_delayed_replies()
    print(f"アラート: {len(result['alerts'])}件")
    print(f"エスカレーション: {len(result['escalations'])}件")
