"""
CrowdWorks案件自動収集パイプライン

処理フロー:
  1. RSS から案件を収集・フィルタリング
  2. Claude API で案件ごとに提案文を自動生成
  3. Slack に承認ボタン付きで通知（Bolt API経由）
  4. CEO がボタンを押すと Playwright で自動応募

使い方:
  - 収集のみ（GitHub Actions向け）: python main.py collect
  - Slackアプリ常駐（サーバー向け）: python main.py serve
"""

import os
import sys
import time

from job_collector import collect_jobs
from proposal_generator import generate_proposal


def run_collect():
    """案件収集 → 提案文生成 → Slack承認通知を送信"""
    # Slack Bolt が使える場合はそちらを使う
    use_bolt = bool(os.environ.get("SLACK_BOT_TOKEN"))

    if use_bolt:
        from slack_sdk import WebClient
        from slack_app import send_job_with_approval
        client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        channel = os.environ.get("SLACK_CHANNEL", "#案件通知")
    else:
        from slack_notifier import send_job_notification, send_summary

    print("=== CrowdWorks 案件収集パイプライン開始 ===")

    # 1. 案件収集
    print("[1/3] 案件を収集中...")
    jobs = collect_jobs()
    print(f"  → 新着案件: {len(jobs)}件")

    if not jobs:
        print("新着案件なし。終了します。")
        if not use_bolt:
            send_summary(total_found=0, total_notified=0, errors=[])
        return

    # 2. 提案文生成 & 3. Slack通知
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

        # API レートリミット対策
        if i < len(jobs):
            time.sleep(2)

    # サマリー
    if not use_bolt:
        send_summary(total_found=len(jobs), total_notified=notified, errors=errors)

    print(f"\n=== 完了: {notified}/{len(jobs)}件 通知済み ===")
    if errors:
        print(f"エラー: {len(errors)}件")
        for e in errors:
            print(f"  - {e}")


def run_serve():
    """Slack Boltアプリを常駐起動（ボタン押下を待ち受け）"""
    from slack_app import app
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    print("⚡ Slack Bolt アプリ起動中...")
    print("  承認ボタンの押下を待ち受けます")
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "collect"

    if cmd == "collect":
        run_collect()
    elif cmd == "serve":
        run_serve()
    else:
        print(f"使い方: python main.py [collect|serve]")
        print(f"  collect  - 案件収集・提案文生成・Slack通知（定期実行用）")
        print(f"  serve    - Slackアプリ常駐（承認ボタン待受）")
        sys.exit(1)
