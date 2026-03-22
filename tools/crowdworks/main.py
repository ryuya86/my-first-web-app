"""
CrowdWorks自動化パイプライン

コマンド:
  python main.py collect   - 新着案件を収集 → 提案文生成 → Slack通知
  python main.py messages  - 未読メッセージを巡回 → AI返信案生成 → Slack通知
  python main.py all       - collect + messages を両方実行
  python main.py serve     - Slackアプリ常駐（承認ボタン待受）
"""

import os
import sys
import time

from job_collector import collect_jobs
from proposal_generator import generate_proposal


def _get_slack_client():
    """Slack Bolt利用可否を判定し、クライアントを返す"""
    use_bolt = bool(os.environ.get("SLACK_BOT_TOKEN"))
    if use_bolt:
        from slack_sdk import WebClient
        client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        channel = os.environ.get("SLACK_CHANNEL", "#案件通知")
        return True, client, channel
    return False, None, None


def run_collect():
    """案件収集 → 提案文生成 → Slack承認通知"""
    use_bolt, client, channel = _get_slack_client()

    if not use_bolt:
        from slack_notifier import send_job_notification, send_summary

    print("=== CrowdWorks 案件収集パイプライン開始 ===")

    print("[1/3] 案件を収集中...")
    jobs = collect_jobs()
    print(f"  → 新着案件: {len(jobs)}件")

    if not jobs:
        print("新着案件なし。終了します。")
        if not use_bolt:
            send_summary(total_found=0, total_notified=0, errors=[])
        return

    notified = 0
    errors = []

    for i, job in enumerate(jobs, 1):
        print(f"[2/3] ({i}/{len(jobs)}) 提案文生成中: {job['title'][:50]}...")

        try:
            proposal = generate_proposal(job)
        except Exception as e:
            error_msg = f"提案文生成エラー [{job['title'][:30]}]: {e}"
            print(f"  → {error_msg}")
            errors.append(error_msg)
            proposal = "（提案文の自動生成に失敗しました。案件ページを確認の上、手動で作成してください。）"

        print(f"[3/3] ({i}/{len(jobs)}) Slack通知中...")

        if use_bolt:
            try:
                from slack_app import send_job_with_approval
                send_job_with_approval(client, channel, job, proposal)
                notified += 1
                print(f"  → 承認ボタン付き通知完了 ✓")
            except Exception as e:
                errors.append(f"Slack通知失敗 [{job['title'][:30]}]: {e}")
        else:
            success = send_job_notification(job, proposal)
            if success:
                notified += 1
                print(f"  → 通知完了 ✓")
            else:
                errors.append(f"Slack通知失敗 [{job['title'][:30]}]")

        if i < len(jobs):
            time.sleep(2)

    if not use_bolt:
        send_summary(total_found=len(jobs), total_notified=notified, errors=errors)

    print(f"\n=== 案件収集完了: {notified}/{len(jobs)}件 通知済み ===")
    if errors:
        print(f"エラー: {len(errors)}件")
        for e in errors:
            print(f"  - {e}")


def run_messages():
    """未読メッセージ巡回 → AI返信案生成 → Slack承認通知"""
    from message_monitor import get_new_messages
    from reply_generator import generate_reply

    use_bolt, client, channel = _get_slack_client()

    if not use_bolt:
        print("[WARN] SLACK_BOT_TOKEN未設定。メッセージ機能にはSlack Bolt APIが必要です。")
        return

    from slack_app import send_message_with_approval

    print("=== CrowdWorks メッセージ巡回開始 ===")

    print("[1/3] 未読メッセージを取得中...")
    try:
        threads = get_new_messages()
    except Exception as e:
        print(f"  → メッセージ取得エラー: {e}")
        return

    print(f"  → 未読スレッド: {len(threads)}件")

    if not threads:
        print("未読メッセージなし。終了します。")
        return

    notified = 0
    errors = []

    for i, thread in enumerate(threads, 1):
        client_name = thread["client_name"]
        print(f"[2/3] ({i}/{len(threads)}) AI返信案生成中: {client_name}...")

        try:
            result = generate_reply(thread)
            reply_text = result["text"]
            phase = result["phase"]
        except Exception as e:
            error_msg = f"返信生成エラー [{client_name}]: {e}"
            print(f"  → {error_msg}")
            errors.append(error_msg)
            continue

        print(f"[3/3] ({i}/{len(threads)}) Slack通知中... (フェーズ: {phase})")

        try:
            send_message_with_approval(client, channel, thread, reply_text, phase)
            notified += 1
            print(f"  → 承認ボタン付き通知完了 ✓")
        except Exception as e:
            errors.append(f"Slack通知失敗 [{client_name}]: {e}")

        if i < len(threads):
            time.sleep(2)

    print(f"\n=== メッセージ巡回完了: {notified}/{len(threads)}件 通知済み ===")
    if errors:
        print(f"エラー: {len(errors)}件")
        for e in errors:
            print(f"  - {e}")


def run_serve():
    """Slack Boltアプリを常駐起動"""
    from slack_app import app
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    print("⚡ Slack Bolt アプリ起動中...")
    print("  案件応募・メッセージ返信の承認ボタンを待ち受けます")
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd == "collect":
        run_collect()
    elif cmd == "messages":
        run_messages()
    elif cmd == "all":
        run_collect()
        print()
        run_messages()
    elif cmd == "serve":
        run_serve()
    else:
        print("使い方: python main.py [collect|messages|all|serve]")
        print("  collect   - 新着案件収集 → 提案文生成 → Slack通知")
        print("  messages  - 未読メッセージ巡回 → AI返信案 → Slack通知")
        print("  all       - collect + messages を両方実行（デフォルト）")
        print("  serve     - Slackアプリ常駐（承認ボタン待受）")
        sys.exit(1)
