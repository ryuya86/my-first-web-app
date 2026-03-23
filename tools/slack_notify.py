"""
Slack通知ヘルパー — たくみんからSlackへの報告を送信

Usage:
  python tools/slack_notify.py job_found '{"title":"案件名","url":"...","score":85,"proposal":"..."}'
  python tools/slack_notify.py message_received '{"client":"名前","preview":"...","thread_url":"..."}'
  python tools/slack_notify.py error '{"task":"collect-jobs","error":"エラー内容"}'
  python tools/slack_notify.py report '{"title":"朝ブリーフィング","body":"内容..."}'
  python tools/slack_notify.py briefing '{"title":"タイトル","body":"内容..."}'
"""

import json
import os
import sys

from slack_sdk import WebClient

BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
CHANNEL = os.environ.get("SLACK_CHANNEL", "#案件通知")
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "ryuya86/my-first-web-app")
APPLY_QUEUE_FILE = os.path.join(os.path.dirname(__file__), "..", "state", "apply_queue.json")


def _load_apply_queue():
    if os.path.exists(APPLY_QUEUE_FILE):
        with open(APPLY_QUEUE_FILE, "r") as f:
            return json.load(f)
    return []


def _save_apply_queue(queue):
    os.makedirs(os.path.dirname(APPLY_QUEUE_FILE), exist_ok=True)
    with open(APPLY_QUEUE_FILE, "w") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)


def _add_to_apply_queue(job_data):
    """応募キューに案件を追加"""
    queue = _load_apply_queue()
    # 重複チェック
    existing_ids = {item["id"] for item in queue}
    if job_data.get("id") not in existing_ids:
        queue.append({
            "id": job_data.get("id", ""),
            "title": job_data.get("title", ""),
            "url": job_data.get("url", ""),
            "proposal": job_data.get("proposal", ""),
            "status": "pending",
        })
        _save_apply_queue(queue)
    return len(queue)


def get_client():
    if not BOT_TOKEN:
        print("[ERROR] SLACK_BOT_TOKEN が未設定です", file=sys.stderr)
        sys.exit(1)
    return WebClient(token=BOT_TOKEN)


def send_job_found(data):
    """新着案件をSlackに通知"""
    client = get_client()
    title = data.get("title", "不明")
    url = data.get("url", "")
    score = data.get("score", 0)
    category = data.get("category", "other")
    summary = data.get("summary", "")[:500]
    proposal = data.get("proposal", "")[:2900]

    score_icon = "🟢" if score >= 80 else "🟡" if score >= 60 else "🟠" if score >= 40 else "🔴"

    # 応募キューに追加（提案文がある場合のみ）
    if proposal:
        _add_to_apply_queue(data)

    # GitHub Actions手動実行URL
    apply_url = f"https://github.com/{GITHUB_REPO}/actions/workflows/takumin.yml"

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"📋 新着案件: {title[:140]}"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*スコア:* {score_icon} {score}点"},
            {"type": "mrkdwn", "text": f"*カテゴリ:* {category}"},
        ]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*概要:*\n{summary}"}},
        {"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "📄 案件を見る"}, "url": url},
        ]},
        {"type": "divider"},
    ]

    if proposal:
        blocks.append({"type": "section", "text": {
            "type": "mrkdwn",
            "text": f"*📝 提案文:*\n```\n{proposal}\n```",
        }})
        blocks.append({"type": "actions", "elements": [
            {"type": "button", "text": {"type": "plain_text", "text": "✅ 応募する"}, "url": apply_url, "style": "primary"},
            {"type": "button", "text": {"type": "plain_text", "text": "❌ スキップ"}, "url": url},
        ]})
        blocks.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f"💡 「応募する」→ GitHub Actionsで `browse-and-apply` を実行してください"},
        ]})

    client.chat_postMessage(channel=CHANNEL, blocks=blocks, text=f"新着案件: {title}")
    print(f"[Slack] job_found 送信完了: {title[:50]}")


def send_message_received(data):
    """クライアントメッセージをSlackに通知"""
    client = get_client()
    client_name = data.get("client", "不明")
    preview = data.get("preview", "")[:500]
    thread_url = data.get("thread_url", "")
    reply_draft = data.get("reply_draft", "")[:2900]
    phase = data.get("phase", "不明")

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"💬 メッセージ: {client_name}"}},
        {"type": "section", "fields": [
            {"type": "mrkdwn", "text": f"*フェーズ:* {phase}"},
            {"type": "mrkdwn", "text": f"*スレッド:* <{thread_url}|開く>"},
        ]},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*受信内容:*\n>{preview}"}},
    ]

    if reply_draft:
        blocks.extend([
            {"type": "divider"},
            {"type": "section", "text": {
                "type": "mrkdwn",
                "text": f"*📝 返信案（承認待ち）:*\n```\n{reply_draft}\n```",
            }},
            {"type": "context", "elements": [
                {"type": "mrkdwn", "text": "⚠️ この返信を送信するにはCEOの承認が必要です"},
            ]},
        ])

    client.chat_postMessage(channel=CHANNEL, blocks=blocks, text=f"メッセージ: {client_name}")
    print(f"[Slack] message_received 送信完了: {client_name}")


def send_error(data):
    """エラーをSlackに通知"""
    client = get_client()
    task = data.get("task", "unknown")
    error = data.get("error", "不明なエラー")
    run_url = data.get("run_url", "")

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"🚨 エラー発生: {task}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"```\n{error[:2000]}\n```"}},
    ]
    if run_url:
        blocks.append({"type": "section", "text": {
            "type": "mrkdwn", "text": f"<{run_url}|GitHub Actionsログを確認>",
        }})

    client.chat_postMessage(channel=CHANNEL, blocks=blocks, text=f"エラー: {task}")
    print(f"[Slack] error 送信完了: {task}")


def send_report(data):
    """レポート・ブリーフィングをSlackに通知"""
    client = get_client()
    title = data.get("title", "レポート")
    body = data.get("body", "")[:3000]

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": f"📊 {title}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": body}},
    ]

    client.chat_postMessage(channel=CHANNEL, blocks=blocks, text=title)
    print(f"[Slack] report 送信完了: {title}")


HANDLERS = {
    "job_found": send_job_found,
    "message_received": send_message_received,
    "error": send_error,
    "report": send_report,
    "briefing": send_report,
}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python tools/slack_notify.py <type> '<json>'")
        print(f"Types: {', '.join(HANDLERS.keys())}")
        sys.exit(1)

    msg_type = sys.argv[1]
    msg_data = json.loads(sys.argv[2])

    handler = HANDLERS.get(msg_type)
    if not handler:
        print(f"[ERROR] Unknown type: {msg_type}. Available: {', '.join(HANDLERS.keys())}")
        sys.exit(1)

    handler(msg_data)
