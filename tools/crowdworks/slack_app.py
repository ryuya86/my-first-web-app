"""
Slack Boltアプリ — 承認ボタン付き通知 & ワンクリック自動応募

起動: python slack_app.py
"""

import json
import os
import logging
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from auto_apply import apply_to_job

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App(token=os.environ["SLACK_BOT_TOKEN"])

# 案件データの一時保存（job_id → {job, proposal}）
pending_jobs = {}

CATEGORY_LABELS = {
    "data_entry": "データ入力",
    "scraping": "スクレイピング",
    "automation": "業務自動化",
    "development": "開発",
    "web_design": "Web制作",
    "other": "その他",
}


def build_job_blocks(job, proposal, job_id):
    """承認ボタン付きのSlackメッセージブロックを生成"""
    category_label = CATEGORY_LABELS.get(job.get("category", "other"), "その他")

    return [
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
                "text": f"*📝 提案文:*\n```\n{proposal[:2900]}\n```",
            },
        },
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ この提案で応募する"},
                    "style": "primary",
                    "action_id": "approve_apply",
                    "value": job_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✏️ 提案文を編集して応募"},
                    "action_id": "edit_proposal",
                    "value": job_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ スキップ"},
                    "style": "danger",
                    "action_id": "skip_job",
                    "value": job_id,
                },
            ],
        },
    ]


def send_job_with_approval(client, channel, job, proposal):
    """承認ボタン付きで案件をSlackに送信"""
    job_id = job["id"]
    pending_jobs[job_id] = {"job": job, "proposal": proposal}

    client.chat_postMessage(
        channel=channel,
        blocks=build_job_blocks(job, proposal, job_id),
        text=f"新着案件: {job['title']}",
    )


# --- ボタンアクションハンドラ ---

@app.action("approve_apply")
def handle_approve(ack, body, client):
    """「この提案で応募する」ボタン"""
    ack()
    job_id = body["actions"][0]["value"]
    channel = body["channel"]["id"]
    ts = body["message"]["ts"]

    data = pending_jobs.get(job_id)
    if not data:
        client.chat_postMessage(channel=channel, text="⚠️ 案件データが見つかりません（期限切れ）")
        return

    # ボタンを「応募処理中...」に差し替え
    client.chat_update(
        channel=channel,
        ts=ts,
        blocks=body["message"]["blocks"][:-1] + [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "⏳ *応募処理中...*"},
            }
        ],
        text="応募処理中...",
    )

    # Playwright で自動応募
    result = apply_to_job(data["job"]["url"], data["proposal"])

    if result["success"]:
        status_block = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"✅ *応募完了!* {result['message']}"},
        }
    else:
        status_block = {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"❌ *応募失敗:* {result['message']}"},
        }

    client.chat_update(
        channel=channel,
        ts=ts,
        blocks=body["message"]["blocks"][:-1] + [status_block],
        text=f"応募結果: {result['message']}",
    )

    pending_jobs.pop(job_id, None)


@app.action("edit_proposal")
def handle_edit(ack, body, client):
    """「提案文を編集して応募」ボタン → モーダル表示"""
    ack()
    job_id = body["actions"][0]["value"]
    data = pending_jobs.get(job_id)

    if not data:
        return

    client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "submit_edited_proposal",
            "private_metadata": json.dumps({
                "job_id": job_id,
                "channel": body["channel"]["id"],
                "ts": body["message"]["ts"],
            }),
            "title": {"type": "plain_text", "text": "提案文を編集"},
            "submit": {"type": "plain_text", "text": "この内容で応募"},
            "close": {"type": "plain_text", "text": "キャンセル"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*案件:* {data['job']['title'][:100]}",
                    },
                },
                {
                    "type": "input",
                    "block_id": "proposal_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "proposal_text",
                        "multiline": True,
                        "initial_value": data["proposal"],
                    },
                    "label": {"type": "plain_text", "text": "提案文"},
                },
            ],
        },
    )


@app.view("submit_edited_proposal")
def handle_edited_submission(ack, body, client):
    """編集済み提案文でのモーダル送信"""
    ack()
    meta = json.loads(body["view"]["private_metadata"])
    job_id = meta["job_id"]
    channel = meta["channel"]
    ts = meta["ts"]

    edited_text = body["view"]["state"]["values"]["proposal_block"]["proposal_text"]["value"]
    data = pending_jobs.get(job_id)

    if not data:
        client.chat_postMessage(channel=channel, text="⚠️ 案件データが見つかりません")
        return

    # ステータス更新
    client.chat_postMessage(channel=channel, text="⏳ 編集済み提案文で応募処理中...")

    result = apply_to_job(data["job"]["url"], edited_text)

    if result["success"]:
        client.chat_postMessage(channel=channel, text=f"✅ *応募完了!* {result['message']}")
    else:
        client.chat_postMessage(channel=channel, text=f"❌ *応募失敗:* {result['message']}")

    pending_jobs.pop(job_id, None)


@app.action("skip_job")
def handle_skip(ack, body, client):
    """「スキップ」ボタン"""
    ack()
    job_id = body["actions"][0]["value"]
    channel = body["channel"]["id"]
    ts = body["message"]["ts"]

    client.chat_update(
        channel=channel,
        ts=ts,
        blocks=body["message"]["blocks"][:-1] + [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "⏭️ *スキップしました*"},
            }
        ],
        text="スキップ",
    )

    pending_jobs.pop(job_id, None)


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    print("⚡ Slack Bolt アプリ起動中...")
    handler.start()
