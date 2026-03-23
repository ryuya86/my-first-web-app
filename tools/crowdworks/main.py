"""
CrowdWorks自動化パイプライン — 全機能統合版

コマンド:
  python main.py collect     - 新着案件を収集 → スコアリング → 提案文生成 → 自動応募/Slack通知
  python main.py messages    - 未読メッセージを巡回 → AI返信案生成 → NGチェック → Slack承認依頼
  python main.py all         - collect + messages を両方実行
  python main.py alerts      - 返信遅延アラート + ヘルスチェックをSlackに送信
  python main.py report      - 週次レポートをSlackに送信
  python main.py monthly     - 月次収益レポートをSlackに送信
  python main.py morning     - 朝のブリーフィングをSlackに送信
  python main.py evening     - 夕方のサマリーをSlackに送信
  python main.py health      - システムヘルスチェックをSlackに送信
  python main.py serve       - Slackアプリ常駐（承認ボタン待受）

環境変数:
  CW_AUTO_APPLY_ENABLED      - true で高スコア案件の自動応募を有効化（デフォルト: false）
  CW_AUTO_APPLY_MIN_SCORE    - 自動応募の最低スコア（デフォルト: 85）
  CW_AUTO_APPLY_MAX_COMPETITORS - 自動応募の最大競合数（デフォルト: 20）
"""

import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from job_collector import collect_jobs
from proposal_generator import generate_proposal
from auto_decision import decide_job_application, log_decision
from auto_apply import apply_to_job
from error_recovery import with_retry, update_health, send_health_alert


def _get_slack_client():
    """Slack Bolt利用可否を判定し、クライアントを返す"""
    use_bolt = bool(os.environ.get("SLACK_BOT_TOKEN"))
    if use_bolt:
        from slack_sdk import WebClient
        client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
        channel = os.environ.get("SLACK_CHANNEL", "#案件通知")
        return True, client, channel
    return False, None, None


@with_retry(max_retries=2, base_delay=3, component="job_collection")
def _collect_jobs_with_retry():
    return collect_jobs()


@with_retry(max_retries=2, base_delay=3, component="proposal_generation")
def _generate_proposal_with_retry(job):
    return generate_proposal(job)


def run_collect():
    """案件収集 → スコアリング → 競合チェック → クライアントスクリーニング → 提案文生成 → Slack通知"""
    from job_scorer import filter_jobs_by_score, format_score_for_slack
    from competitor_monitor import prioritize_by_competition, format_competition_for_slack
    from history_db import log_application

    use_bolt, client, channel = _get_slack_client()

    if not use_bolt:
        from slack_notifier import send_job_notification, send_summary

    print("=== CrowdWorks 案件収集パイプライン開始 ===")

    # 1. 案件収集
    print("[1/5] 案件を収集中...")
    try:
        jobs = _collect_jobs_with_retry()
    except Exception as e:
        print(f"  → 案件収集エラー: {e}")
        return
    print(f"  → 新着案件: {len(jobs)}件")

    if not jobs:
        print("新着案件なし。終了します。")
        if not use_bolt:
            send_summary(total_found=0, total_notified=0, errors=[])
        return

    # 2. AIスコアリング
    print("[2/5] マッチングスコアリング中...")
    try:
        passed, skipped = filter_jobs_by_score(jobs)
        print(f"  → 通過: {len(passed)}件 / スキップ: {len(skipped)}件")
        for s in skipped:
            print(f"    スキップ: {s['title'][:40]}... (スコア: {s.get('match_score', 0)})")
    except Exception as e:
        print(f"  → スコアリングエラー (全件通過扱い): {e}")
        passed = jobs
        skipped = []

    if not passed:
        print("全案件がスコア閾値未満。終了します。")
        return

    # 3. 競合応募者数チェック
    print("[3/5] 競合応募者数を取得中...")
    try:
        passed = prioritize_by_competition(passed)
        update_health("competitor_monitor", True)
    except Exception as e:
        print(f"  → 競合チェックエラー (スキップ): {e}")
        update_health("competitor_monitor", False, str(e))

    # 4. 提案文生成 & 5. 自動判定 & 6. 応募 or Slack通知
    notified = 0
    auto_applied = 0
    errors = []

    for i, job in enumerate(passed, 1):
        print(f"[4/6] ({i}/{len(passed)}) 提案文生成中: {job['title'][:50]}...")

        try:
            proposal = _generate_proposal_with_retry(job)
        except Exception as e:
            error_msg = f"提案文生成エラー [{job['title'][:30]}]: {e}"
            print(f"  → {error_msg}")
            errors.append(error_msg)
            proposal = "（提案文の自動生成に失敗しました。案件ページを確認の上、手動で作成してください。）"

        # DB記録
        try:
            log_application(
                job, proposal,
                match_score=job.get("match_score", 0),
                competitor_count=job.get("competitor_count", 0),
            )
        except Exception as e:
            print(f"  → DB記録エラー (続行): {e}")

        # 5. 自動判定
        decision = decide_job_application(job, proposal)
        print(f"[5/6] ({i}/{len(passed)}) 判定: {decision.action} ({decision.reason})")

        try:
            log_decision(decision, job, proposal)
        except Exception as e:
            print(f"  → 判定ログエラー (続行): {e}")

        # 6. 判定結果に基づく処理
        if decision.action == "auto_execute":
            # 自動応募
            print(f"[6/6] ({i}/{len(passed)}) 自動応募実行中...")
            try:
                result = apply_to_job(job["url"], proposal)
                if result["success"]:
                    auto_applied += 1
                    print(f"  → 自動応募完了 ✓")
                else:
                    print(f"  → 自動応募失敗: {result['message']}")
                    errors.append(f"自動応募失敗 [{job['title'][:30]}]: {result['message']}")

                # Slackに結果報告（ボタンなし）
                if use_bolt:
                    from slack_app import send_auto_applied_notification
                    send_auto_applied_notification(client, channel, job, proposal, decision, result)
                notified += 1
            except Exception as e:
                errors.append(f"自動応募エラー [{job['title'][:30]}]: {e}")

        elif decision.action == "request_approval":
            # 既存の承認フロー
            print(f"[6/6] ({i}/{len(passed)}) Slack承認依頼中...")
            if use_bolt:
                try:
                    from slack_app import send_job_with_approval_v2
                    send_job_with_approval_v2(client, channel, job, proposal)
                    notified += 1
                    print(f"  → 通知完了 ✓")
                except Exception as e:
                    errors.append(f"Slack通知失敗 [{job['title'][:30]}]: {e}")
            else:
                success = send_job_notification(job, proposal)
                if success:
                    notified += 1
                else:
                    errors.append(f"Slack通知失敗 [{job['title'][:30]}]")

        else:
            # reject → スキップ
            print(f"  → スキップ（{decision.reason}）")

        if i < len(passed):
            time.sleep(2)

    if not use_bolt:
        send_summary(total_found=len(jobs), total_notified=notified, errors=errors)

    update_health("collect_pipeline", success=len(errors) == 0,
                  message=f"{notified}/{len(passed)}件通知完了 (自動応募: {auto_applied}件)")

    print(f"\n=== 案件収集完了: {notified}/{len(passed)}件処理 (自動応募: {auto_applied}件, スキップ: {len(skipped)}件) ===")
    if errors:
        print(f"エラー: {len(errors)}件")
        for e in errors:
            print(f"  - {e}")


def run_messages():
    """未読メッセージ巡回 → AI返信案生成 → NGチェック → DB記録 → Slack承認通知"""
    from message_monitor import get_new_messages
    from reply_generator import generate_reply
    from history_db import log_message

    use_bolt, client, channel = _get_slack_client()

    if not use_bolt:
        print("[WARN] SLACK_BOT_TOKEN未設定。メッセージ機能にはSlack Bolt APIが必要です。")
        return

    from slack_app import send_message_with_approval

    print("=== CrowdWorks メッセージ巡回開始 ===")

    print("[1/3] 未読メッセージを取得中...")
    try:
        threads = get_new_messages()
        update_health("message_monitor", True)
    except Exception as e:
        print(f"  → メッセージ取得エラー: {e}")
        update_health("message_monitor", False, str(e))
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

        # NGチェック結果表示
        if not result.get("ng_safe", True):
            has_errors = result.get("ng_has_errors", False)
            violation_count = len(result.get("ng_violations", []))
            level = "エラー" if has_errors else "警告"
            print(f"  → ⚠️ NGチェック: {level} {violation_count}件検出")

        # DB記録
        try:
            job_info = thread.get("job_info", {})
            log_message(
                thread_id=thread["thread_id"],
                thread_url=thread["thread_url"],
                client_name=client_name,
                job_id=job_info.get("job_url", ""),
                job_title=job_info.get("job_title", ""),
                phase=phase,
                direction="received",
                body=thread.get("latest_message", ""),
                reply_generated=reply_text,
                ng_violations=str(result.get("ng_violations", [])),
                action="pending",
            )
        except Exception as e:
            print(f"  → DB記録エラー (続行): {e}")

        print(f"[3/3] ({i}/{len(threads)}) Slack通知中... (フェーズ: {phase})")

        try:
            send_message_with_approval(client, channel, thread, reply_text, phase, result)
            notified += 1
            print(f"  → 通知完了 ✓")
        except Exception as e:
            errors.append(f"Slack通知失敗 [{client_name}]: {e}")

        if i < len(threads):
            time.sleep(2)

    update_health("message_pipeline", success=len(errors) == 0,
                  message=f"{notified}/{len(threads)}件通知完了")

    print(f"\n=== メッセージ巡回完了: {notified}/{len(threads)}件 通知済み ===")
    if errors:
        print(f"エラー: {len(errors)}件")
        for e in errors:
            print(f"  - {e}")


def run_alerts():
    """返信遅延アラート + ヘルスチェック"""
    from delay_alert import send_delay_alerts
    from error_recovery import send_health_alert

    use_bolt, client, channel = _get_slack_client()
    if not use_bolt:
        print("[WARN] SLACK_BOT_TOKEN未設定")
        return

    print("=== アラートチェック ===")
    delay_sent = send_delay_alerts(client, channel)
    print(f"  返信遅延アラート: {'送信' if delay_sent else 'なし'}")

    health_sent = send_health_alert(client, channel)
    print(f"  ヘルスアラート: {'送信' if health_sent else 'なし'}")


def run_weekly_report():
    """週次レポート"""
    from weekly_report import send_weekly_report
    use_bolt, client, channel = _get_slack_client()
    if not use_bolt:
        print("[WARN] SLACK_BOT_TOKEN未設定")
        return
    send_weekly_report(client, channel)
    print("週次レポート送信完了")


def run_monthly_report():
    """月次収益レポート"""
    from weekly_report import send_monthly_report
    use_bolt, client, channel = _get_slack_client()
    if not use_bolt:
        print("[WARN] SLACK_BOT_TOKEN未設定")
        return
    year_month = sys.argv[2] if len(sys.argv) > 2 else None
    send_monthly_report(client, channel, year_month)
    print("月次収益レポート送信完了")


def run_morning():
    """朝のブリーフィング"""
    from weekly_report import send_morning_briefing
    use_bolt, client, channel = _get_slack_client()
    if not use_bolt:
        print("[WARN] SLACK_BOT_TOKEN未設定")
        return
    send_morning_briefing(client, channel)
    print("朝のブリーフィング送信完了")


def run_evening():
    """夕方のサマリー"""
    from weekly_report import send_evening_summary
    use_bolt, client, channel = _get_slack_client()
    if not use_bolt:
        print("[WARN] SLACK_BOT_TOKEN未設定")
        return
    send_evening_summary(client, channel)
    print("夕方のサマリー送信完了")


def run_health():
    """ヘルスチェック"""
    from error_recovery import send_health_alert, format_health_for_slack, get_health_report
    use_bolt, client, channel = _get_slack_client()

    report = get_health_report()
    if not report:
        print("ヘルスデータなし")
        return

    status_icons = {"ok": "🟢", "degraded": "🟡", "down": "🔴"}
    for entry in report:
        icon = status_icons.get(entry.get("status", "ok"), "⚪")
        print(f"  {icon} {entry['component']}: {entry.get('message', '')}")

    if use_bolt:
        send_health_alert(client, channel)


def run_serve():
    """Slack Boltアプリを常駐起動"""
    from slack_app import app
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    print("⚡ Slack Bolt アプリ起動中...")
    print("  案件応募・メッセージ返信の承認ボタンを待ち受けます")
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    handler.start()


COMMANDS = {
    "collect": run_collect,
    "messages": run_messages,
    "all": lambda: (run_collect(), print(), run_messages()),
    "alerts": run_alerts,
    "report": run_weekly_report,
    "monthly": run_monthly_report,
    "morning": run_morning,
    "evening": run_evening,
    "health": run_health,
    "serve": run_serve,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd in COMMANDS:
        COMMANDS[cmd]()
    else:
        print("使い方: python main.py [コマンド]")
        print()
        print("コマンド:")
        print("  collect   - 新着案件収集 → スコアリング → 提案文生成 → 自動応募/Slack通知")
        print("  messages  - 未読メッセージ巡回 → AI返信案 → NGチェック → Slack承認依頼")
        print("  all       - collect + messages を両方実行（デフォルト）")
        print("  alerts    - 返信遅延アラート + ヘルスチェック")
        print("  report    - 週次レポートをSlackに送信")
        print("  monthly   - 月次収益レポートをSlackに送信")
        print("  morning   - 朝のブリーフィングをSlackに送信")
        print("  evening   - 夕方のサマリーをSlackに送信")
        print("  health    - システムヘルスチェック")
        print("  serve     - Slackアプリ常駐（承認ボタン待受）")
        sys.exit(1)
