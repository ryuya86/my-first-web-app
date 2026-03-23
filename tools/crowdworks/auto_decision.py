"""
自動応募判定エンジン — 案件のスコア・競合・NGチェックに基づき自動応募可否を判定

判定ルール:
  auto_execute:      match_score >= 85 AND NGチェックOK AND 競合 < 20
  request_approval:  match_score >= 40 AND NGエラーなし → Slack承認フロー
  reject:            match_score < 40 OR NGエラーあり → スキップ

環境変数:
  CW_AUTO_APPLY_ENABLED      - true で自動応募を有効化（デフォルト: false）
  CW_AUTO_APPLY_MIN_SCORE    - 自動応募の最低スコア（デフォルト: 85）
  CW_AUTO_APPLY_MAX_COMPETITORS - 自動応募の最大競合数（デフォルト: 20）
"""

import json
import os
from dataclasses import dataclass, asdict

from ng_checker import check_ng_words


@dataclass
class Decision:
    action: str       # "auto_execute" | "request_approval" | "reject"
    reason: str
    confidence: float  # 0.0-1.0
    risk_level: str    # "low" | "medium" | "high"


# 設定値（環境変数でオーバーライド可能）
AUTO_APPLY_ENABLED = os.environ.get("CW_AUTO_APPLY_ENABLED", "false").lower() == "true"
MIN_SCORE = int(os.environ.get("CW_AUTO_APPLY_MIN_SCORE", "85"))
MAX_COMPETITORS = int(os.environ.get("CW_AUTO_APPLY_MAX_COMPETITORS", "20"))
APPROVAL_THRESHOLD = 40  # 既存の閾値


def decide_job_application(job, proposal):
    """
    案件と提案文から自動応募の可否を判定する。

    Returns:
        Decision: 判定結果
    """
    score = job.get("match_score", 0) or 0
    competitors = job.get("competitor_count", 0) or 0

    # 1. スコアが閾値未満 → reject
    if score < APPROVAL_THRESHOLD:
        return Decision(
            action="reject",
            reason=f"スコア{score}点が閾値{APPROVAL_THRESHOLD}未満",
            confidence=0.9,
            risk_level="low",
        )

    # 2. 提案文のNGチェック
    ng_result = check_ng_words(proposal)
    has_ng_errors = any(v["severity"] == "error" for v in ng_result.violations)

    if has_ng_errors:
        return Decision(
            action="reject",
            reason=f"提案文にNGエラー検出: {[v['label'] for v in ng_result.violations if v['severity'] == 'error']}",
            confidence=0.95,
            risk_level="high",
        )

    # 3. 自動応募が無効 → 全て承認フロー
    if not AUTO_APPLY_ENABLED:
        return Decision(
            action="request_approval",
            reason="自動応募が無効（CW_AUTO_APPLY_ENABLED=false）",
            confidence=1.0,
            risk_level="low",
        )

    # 4. 高スコア + 低競合 → 自動実行
    if score >= MIN_SCORE and competitors < MAX_COMPETITORS:
        return Decision(
            action="auto_execute",
            reason=f"スコア{score}点(>={MIN_SCORE}) & 競合{competitors}名(<{MAX_COMPETITORS})",
            confidence=score / 100.0,
            risk_level="low",
        )

    # 5. それ以外 → 承認フロー
    reasons = []
    if score < MIN_SCORE:
        reasons.append(f"スコア{score}点(<{MIN_SCORE})")
    if competitors >= MAX_COMPETITORS:
        reasons.append(f"競合{competitors}名(>={MAX_COMPETITORS})")

    return Decision(
        action="request_approval",
        reason="承認必要: " + ", ".join(reasons),
        confidence=score / 100.0,
        risk_level="medium",
    )


def log_decision(decision, job, proposal=""):
    """判定結果をDBに記録"""
    from history_db import log_auto_decision

    context = {
        "job_id": job.get("id", ""),
        "job_title": job.get("title", ""),
        "match_score": job.get("match_score", 0),
        "competitor_count": job.get("competitor_count", 0),
    }

    log_auto_decision(
        decision_type="job_application",
        action=decision.action,
        reason=decision.reason,
        confidence=decision.confidence,
        risk_level=decision.risk_level,
        context_json=json.dumps(context, ensure_ascii=False),
    )


if __name__ == "__main__":
    # テスト
    test_cases = [
        {"title": "高スコア案件", "match_score": 90, "competitor_count": 5},
        {"title": "中スコア案件", "match_score": 60, "competitor_count": 10},
        {"title": "低スコア案件", "match_score": 30, "competitor_count": 3},
        {"title": "高競合案件", "match_score": 90, "competitor_count": 25},
    ]

    print(f"自動応募: {'有効' if AUTO_APPLY_ENABLED else '無効'}")
    print(f"閾値: スコア>={MIN_SCORE}, 競合<{MAX_COMPETITORS}\n")

    for job in test_cases:
        d = decide_job_application(job, "テスト提案文です。")
        print(f"  {job['title']}: {d.action} ({d.reason})")
