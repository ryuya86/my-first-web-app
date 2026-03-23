"""
Slack通知モジュール — 案件情報と提案文をSlackに送信
"""

import json
import os
import requests

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

CATEGORY_LABELS = {
    "data_entry": "データ入力",
    "scraping": "スクレイピング",
    "automation": "業務自動化",
    "development": "開発",
    "web_design": "Web制作",
    "other": "その他",
}


def send_job_notification(job, proposal):
    """案件情報と提案文をSlackに送信"""
    if not SLACK_WEBHOOK_URL:
        print("[WARN] SLACK_WEBHOOK_URL が設定されていません")
        return False

    category_label = CATEGORY_LABELS.get(job.get("category", "other"), "その他")

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"📋 新着案件: {job['title'][:140]}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*カテゴリ:*\n{category_label}"},
                {"type": "mrkdwn", "text": f"*検索KW:*\n{job.get('search_keyword', '-')}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*案件概要:*\n{job['summary'][:500]}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"<{job['url']}|🔗 案件ページを開く>",
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*📝 生成済み提案文（コピペ用）:*\n```\n{proposal[:2900]}\n```",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "⚠️ 提案文は案件ページの内容を確認の上、必要に応じて修正してから応募してください",
                }
            ],
        },
        {"type": "divider"},
    ]

    payload = {"blocks": blocks}

    try:
        response = requests.post(
            SLACK_WEBHOOK_URL,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"[ERROR] Slack送信失敗: {e}")
        return False


def send_summary(total_found, total_notified, errors):
    """実行サマリーをSlackに送信"""
    if not SLACK_WEBHOOK_URL:
        return False

    status = "✅ 正常完了" if not errors else f"⚠️ {len(errors)}件のエラー"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📊 CrowdWorks案件収集レポート",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*ステータス:*\n{status}"},
                {"type": "mrkdwn", "text": f"*新着案件数:*\n{total_found}件"},
                {"type": "mrkdwn", "text": f"*通知済み:*\n{total_notified}件"},
            ],
        },
    ]

    if errors:
        error_text = "\n".join(f"• {e}" for e in errors[:5])
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*エラー詳細:*\n{error_text}"},
        })

    payload = {"blocks": blocks}

    try:
        response = requests.post(SLACK_WEBHOOK_URL, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.RequestException as e:
        print(f"[ERROR] サマリー送信失敗: {e}")
        return False
