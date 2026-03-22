"""
Slack Boltアプリ — 承認ボタン付き通知 & ワンクリック自動応募 & メッセージ返信

起動: python slack_app.py
"""

import json
import os
import logging
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from auto_apply import apply_to_job
from message_sender import send_reply as send_cw_reply

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = App(token=os.environ["SLACK_BOT_TOKEN"])

# 一時保存ストア
pending_jobs = {}       # job_id → {job, proposal}
pending_replies = {}    # thread_id → {thread, reply}

CATEGORY_LABELS = {
    "data_entry": "データ入力",
    "scraping": "スクレイピング",
    "automation": "業務自動化",
    "development": "開発",
    "web_design": "Web制作",
    "other": "その他",
}

PHASE_LABELS = {
    "pre_contract": "📨 応募後〜契約前",
    "in_progress": "🔨 案件進行中",
    "delivery": "📦 納品・検収",
    "follow_up": "🤝 フォローアップ",
}


# ============================================================
# 案件応募関連（既存）
# ============================================================

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
                    "text": {"type": "plain_text", "text": "✏️ 編集して応募"},
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


@app.action("approve_apply")
def handle_approve(ack, body, client):
    ack()
    job_id = body["actions"][0]["value"]
    channel = body["channel"]["id"]
    ts = body["message"]["ts"]

    data = pending_jobs.get(job_id)
    if not data:
        client.chat_postMessage(channel=channel, text="⚠️ 案件データが見つかりません（期限切れ）")
        return

    client.chat_update(
        channel=channel, ts=ts,
        blocks=body["message"]["blocks"][:-1] + [
            {"type": "section", "text": {"type": "mrkdwn", "text": "⏳ *応募処理中...*"}}
        ],
        text="応募処理中...",
    )

    result = apply_to_job(data["job"]["url"], data["proposal"])
    status = f"✅ *応募完了!* {result['message']}" if result["success"] else f"❌ *応募失敗:* {result['message']}"

    client.chat_update(
        channel=channel, ts=ts,
        blocks=body["message"]["blocks"][:-1] + [
            {"type": "section", "text": {"type": "mrkdwn", "text": status}}
        ],
        text=f"応募結果: {result['message']}",
    )
    pending_jobs.pop(job_id, None)


@app.action("edit_proposal")
def handle_edit(ack, body, client):
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
                {"type": "section", "text": {"type": "mrkdwn", "text": f"*案件:* {data['job']['title'][:100]}"}},
                {
                    "type": "input", "block_id": "proposal_block",
                    "element": {"type": "plain_text_input", "action_id": "proposal_text", "multiline": True, "initial_value": data["proposal"]},
                    "label": {"type": "plain_text", "text": "提案文"},
                },
            ],
        },
    )


@app.view("submit_edited_proposal")
def handle_edited_submission(ack, body, client):
    ack()
    meta = json.loads(body["view"]["private_metadata"])
    job_id = meta["job_id"]
    channel = meta["channel"]
    edited_text = body["view"]["state"]["values"]["proposal_block"]["proposal_text"]["value"]
    data = pending_jobs.get(job_id)

    if not data:
        client.chat_postMessage(channel=channel, text="⚠️ 案件データが見つかりません")
        return

    client.chat_postMessage(channel=channel, text="⏳ 編集済み提案文で応募処理中...")
    result = apply_to_job(data["job"]["url"], edited_text)
    status = f"✅ *応募完了!* {result['message']}" if result["success"] else f"❌ *応募失敗:* {result['message']}"
    client.chat_postMessage(channel=channel, text=status)
    pending_jobs.pop(job_id, None)


@app.action("skip_job")
def handle_skip(ack, body, client):
    ack()
    job_id = body["actions"][0]["value"]
    channel = body["channel"]["id"]
    ts = body["message"]["ts"]

    client.chat_update(
        channel=channel, ts=ts,
        blocks=body["message"]["blocks"][:-1] + [
            {"type": "section", "text": {"type": "mrkdwn", "text": "⏭️ *スキップしました*"}}
        ],
        text="スキップ",
    )
    pending_jobs.pop(job_id, None)


# ============================================================
# メッセージ返信関連（新規）
# ============================================================

def build_message_blocks(thread, reply_text, phase):
    """メッセージ承認通知のブロックを生成"""
    thread_id = thread["thread_id"]
    client_name = thread["client_name"]
    job_title = thread.get("job_info", {}).get("job_title", "不明")
    phase_label = PHASE_LABELS.get(phase, "不明")

    # 直近の会話を表示（最新3件）
    recent = thread["messages"][-3:]
    convo_lines = []
    for m in recent:
        tag = "💬 自分" if m["is_mine"] else f"👤 {client_name}"
        convo_lines.append(f"*{tag}:*\n{m['body'][:200]}")
    conversation_text = "\n\n".join(convo_lines)

    return [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"💬 新着メッセージ: {client_name}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*案件:*\n{job_title[:60]}"},
                {"type": "mrkdwn", "text": f"*フェーズ:*\n{phase_label}"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"<{thread['thread_url']}|🔗 CrowdWorksで会話を開く>",
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*最近のやりとり:*\n{conversation_text[:1500]}",
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🤖 AI返信案:*\n```\n{reply_text[:2900]}\n```",
            },
        },
        {"type": "divider"},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✅ この返信を送信"},
                    "style": "primary",
                    "action_id": "approve_reply",
                    "value": thread_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "✏️ 編集して送信"},
                    "action_id": "edit_reply",
                    "value": thread_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "❌ スキップ"},
                    "style": "danger",
                    "action_id": "skip_reply",
                    "value": thread_id,
                },
            ],
        },
    ]


def send_message_with_approval(client, channel, thread, reply_text, phase):
    """承認ボタン付きでメッセージ返信案をSlackに送信"""
    thread_id = thread["thread_id"]
    pending_replies[thread_id] = {"thread": thread, "reply": reply_text}

    client.chat_postMessage(
        channel=channel,
        blocks=build_message_blocks(thread, reply_text, phase),
        text=f"新着メッセージ: {thread['client_name']}",
    )


@app.action("approve_reply")
def handle_approve_reply(ack, body, client):
    """「この返信を送信」ボタン"""
    ack()
    thread_id = body["actions"][0]["value"]
    channel = body["channel"]["id"]
    ts = body["message"]["ts"]

    data = pending_replies.get(thread_id)
    if not data:
        client.chat_postMessage(channel=channel, text="⚠️ メッセージデータが見つかりません（期限切れ）")
        return

    client.chat_update(
        channel=channel, ts=ts,
        blocks=body["message"]["blocks"][:-1] + [
            {"type": "section", "text": {"type": "mrkdwn", "text": "⏳ *返信送信中...*"}}
        ],
        text="返信送信中...",
    )

    result = send_cw_reply(data["thread"]["thread_url"], data["reply"])

    if result["success"]:
        status = f"✅ *返信送信完了!*"
    else:
        status = f"❌ *送信失敗:* {result['message']}"

    client.chat_update(
        channel=channel, ts=ts,
        blocks=body["message"]["blocks"][:-1] + [
            {"type": "section", "text": {"type": "mrkdwn", "text": status}}
        ],
        text=status,
    )
    pending_replies.pop(thread_id, None)


@app.action("edit_reply")
def handle_edit_reply(ack, body, client):
    """「編集して送信」ボタン → モーダル表示"""
    ack()
    thread_id = body["actions"][0]["value"]
    data = pending_replies.get(thread_id)
    if not data:
        return

    client.views_open(
        trigger_id=body["trigger_id"],
        view={
            "type": "modal",
            "callback_id": "submit_edited_reply",
            "private_metadata": json.dumps({
                "thread_id": thread_id,
                "channel": body["channel"]["id"],
                "ts": body["message"]["ts"],
            }),
            "title": {"type": "plain_text", "text": "返信を編集"},
            "submit": {"type": "plain_text", "text": "この内容で送信"},
            "close": {"type": "plain_text", "text": "キャンセル"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*クライアント:* {data['thread']['client_name']}\n*最新メッセージ:*\n> {data['thread']['latest_message'][:300]}",
                    },
                },
                {
                    "type": "input", "block_id": "reply_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "reply_text",
                        "multiline": True,
                        "initial_value": data["reply"],
                    },
                    "label": {"type": "plain_text", "text": "返信文"},
                },
            ],
        },
    )


@app.view("submit_edited_reply")
def handle_edited_reply_submission(ack, body, client):
    """編集済み返信のモーダル送信"""
    ack()
    meta = json.loads(body["view"]["private_metadata"])
    thread_id = meta["thread_id"]
    channel = meta["channel"]

    edited_text = body["view"]["state"]["values"]["reply_block"]["reply_text"]["value"]
    data = pending_replies.get(thread_id)

    if not data:
        client.chat_postMessage(channel=channel, text="⚠️ メッセージデータが見つかりません")
        return

    client.chat_postMessage(channel=channel, text="⏳ 編集済み返信を送信中...")
    result = send_cw_reply(data["thread"]["thread_url"], edited_text)

    status = f"✅ *返信送信完了!*" if result["success"] else f"❌ *送信失敗:* {result['message']}"
    client.chat_postMessage(channel=channel, text=status)
    pending_replies.pop(thread_id, None)


@app.action("skip_reply")
def handle_skip_reply(ack, body, client):
    """「スキップ」ボタン"""
    ack()
    thread_id = body["actions"][0]["value"]
    channel = body["channel"]["id"]
    ts = body["message"]["ts"]

    client.chat_update(
        channel=channel, ts=ts,
        blocks=body["message"]["blocks"][:-1] + [
            {"type": "section", "text": {"type": "mrkdwn", "text": "⏭️ *スキップしました*"}}
        ],
        text="スキップ",
    )
    pending_replies.pop(thread_id, None)


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    print("⚡ Slack Bolt アプリ起動中...")
    handler.start()
