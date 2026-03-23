"""
案件マッチングスコアリング — AIで案件を0〜100点にスコアリング
"""

import anthropic
import json
import os

MODEL = "claude-haiku-4-5-20251001"

# スコアリング基準の閾値
DEFAULT_MIN_SCORE = int(os.environ.get("CW_MIN_MATCH_SCORE", "40"))

SCORING_PROMPT = """
以下のCrowdWorks案件を0〜100点でスコアリングしてください。

【現在のフェーズ】
実績作りの段階です。報酬より経験・実績を優先します。

【評価基準】
1. 自動化適性 (0-35点): AI・RPA・スクレイピング・データ処理など自動化で効率化できる案件か（最重視）
2. 報酬妥当性 (0-20点): 作業量に対して報酬が妥当か（時給換算1,000円以上なら許容。実績作りのため低報酬でもOK）
3. 明確性 (0-15点): 要件・成果物の明確さ（面談で詳細を詰められるため、多少曖昧でも減点しすぎない）
4. リスク (0-30点): トラブルリスクが低いか（過剰な期待・短すぎる納期・連絡が取れなさそうな案件は大幅減点）

【案件情報】
タイトル: {title}
カテゴリ: {category}
報酬: {budget}
概要:
{summary}

【出力形式】
以下のJSONのみを出力してください:
{{
  "total_score": <0-100の整数>,
  "breakdown": {{
    "automation_fit": <0-25>,
    "budget_fairness": <0-25>,
    "clarity": <0-25>,
    "low_risk": <0-25>
  }},
  "reason": "<1文でスコアの理由>",
  "recommended": <true/false>
}}
"""


def score_job(job: dict) -> dict:
    """案件をAIでスコアリング"""
    client = anthropic.Anthropic()

    budget_str = ""
    if job.get("budget_min") and job.get("budget_max"):
        budget_str = f"{job['budget_min']:,}〜{job['budget_max']:,}円"
    elif job.get("budget_max"):
        budget_str = f"〜{job['budget_max']:,}円"
    elif job.get("budget_min"):
        budget_str = f"{job['budget_min']:,}円〜"
    else:
        budget_str = "記載なし"

    prompt = SCORING_PROMPT.format(
        title=job.get("title", ""),
        category=job.get("category", ""),
        budget=budget_str,
        summary=job.get("summary", "")[:1000],
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )

    response_text = message.content[0].text.strip()

    # JSONを抽出（```json ... ``` で囲まれている場合も対応）
    if "```" in response_text:
        json_str = response_text.split("```")[1]
        if json_str.startswith("json"):
            json_str = json_str[4:]
    else:
        json_str = response_text

    try:
        result = json.loads(json_str.strip())
    except json.JSONDecodeError:
        result = {
            "total_score": 50,
            "breakdown": {"automation_fit": 12, "budget_fairness": 12, "clarity": 13, "low_risk": 13},
            "reason": "スコアリング結果のパースに失敗（デフォルト値）",
            "recommended": True,
        }

    return result


def filter_jobs_by_score(jobs: list, min_score: int = None) -> tuple[list, list]:
    """案件リストをスコアリングし、閾値以上/未満に分類"""
    if min_score is None:
        min_score = DEFAULT_MIN_SCORE

    passed = []
    skipped = []

    for job in jobs:
        result = score_job(job)
        job["match_score"] = result["total_score"]
        job["score_breakdown"] = result["breakdown"]
        job["score_reason"] = result["reason"]
        job["score_recommended"] = result["recommended"]

        if result["total_score"] >= min_score:
            passed.append(job)
        else:
            skipped.append(job)

    # スコア高い順にソート
    passed.sort(key=lambda j: j["match_score"], reverse=True)

    return passed, skipped


def format_score_for_slack(job: dict) -> str:
    """Slack表示用のスコア文字列を生成"""
    score = job.get("match_score", 0)
    breakdown = job.get("score_breakdown", {})
    reason = job.get("score_reason", "")

    if score >= 80:
        icon = "🟢"
    elif score >= 60:
        icon = "🟡"
    elif score >= 40:
        icon = "🟠"
    else:
        icon = "🔴"

    parts = [
        f"自動化:{breakdown.get('automation_fit', 0)}",
        f"報酬:{breakdown.get('budget_fairness', 0)}",
        f"明確性:{breakdown.get('clarity', 0)}",
        f"低リスク:{breakdown.get('low_risk', 0)}",
    ]

    return f"{icon} *{score}点* ({' / '.join(parts)})\n_{reason}_"


if __name__ == "__main__":
    test_job = {
        "title": "Webサイトから商品データ500件をスプレッドシートに入力",
        "category": "data_entry",
        "budget_min": 10000,
        "budget_max": 30000,
        "summary": "ECサイトの商品情報（名前、価格、画像URL、説明文）を指定のGoogleスプレッドシートに入力する作業です。500件の商品があります。納期は1週間です。",
    }
    result = score_job(test_job)
    print(json.dumps(result, ensure_ascii=False, indent=2))
