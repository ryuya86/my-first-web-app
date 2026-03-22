"""
CrowdWorks案件自動収集パイプライン

処理フロー:
  1. RSS から案件を収集・フィルタリング
  2. Claude API で案件ごとに提案文を自動生成
  3. Slack に案件情報 + 提案文を通知
"""

import sys
import time
from job_collector import collect_jobs
from proposal_generator import generate_proposal
from slack_notifier import send_job_notification, send_summary


def run():
    print("=== CrowdWorks 案件収集パイプライン開始 ===")

    # 1. 案件収集
    print("[1/3] 案件を収集中...")
    jobs = collect_jobs()
    print(f"  → 新着案件: {len(jobs)}件")

    if not jobs:
        print("新着案件なし。終了します。")
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
        success = send_job_notification(job, proposal)
        if success:
            notified += 1
            print(f"  → 通知完了 ✓")
        else:
            errors.append(f"Slack通知失敗 [{job['title'][:30]}]")

        # API レートリミット対策
        if i < len(jobs):
            time.sleep(2)

    # サマリー送信
    send_summary(total_found=len(jobs), total_notified=notified, errors=errors)

    print(f"\n=== 完了: {notified}/{len(jobs)}件 通知済み ===")
    if errors:
        print(f"エラー: {len(errors)}件")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    run()
