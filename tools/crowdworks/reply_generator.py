"""
AI返信文生成モジュール — 会話履歴と案件フェーズに応じた返信を生成
"""

import anthropic
import os

MODEL = "claude-sonnet-4-6"

# 案件フェーズの自動判定キーワード
PHASE_KEYWORDS = {
    "pre_contract": [
        "ご応募", "提案", "ご質問", "お見積", "ご検討",
        "お願いできますか", "可能でしょうか", "ご対応いただけ",
        "仕様", "要件", "予算", "納期", "スケジュール",
    ],
    "in_progress": [
        "進捗", "途中経過", "確認", "修正", "フィードバック",
        "お送りします", "納品", "途中", "作業中",
        "検収", "チェック", "レビュー",
    ],
    "delivery": [
        "完了", "納品", "お納め", "最終版", "Final",
        "検収", "請求", "お支払い",
    ],
    "follow_up": [
        "ありがとう", "評価", "星", "レビュー",
        "またお願い", "次回", "継続", "リピート",
        "ご縁", "感謝",
    ],
}

# フェーズ別のシステムプロンプト
PHASE_PROMPTS = {
    "pre_contract": """
あなたはCrowdWorksで受託業務を行うフリーランスです。
応募後〜契約前の段階で、クライアントとやり取りしています。

【対応方針】
- 質問には具体的かつ明確に回答する
- 見積り・納期の質問には、幅を持たせつつ前向きに回答
- 追加要件があれば確認しつつ柔軟に対応する姿勢を見せる
- 価格交渉には、スコープを明確にしつつ歩み寄る

【トーン】
- 丁寧だが堅すぎない
- 「お世話になっております」で始める
- 迅速な対応力をアピール
""",
    "in_progress": """
あなたはCrowdWorksで受託業務を行うフリーランスです。
案件進行中の段階で、クライアントとやり取りしています。

【対応方針】
- 進捗報告は数字や具体的な内容を含める
- 修正依頼には前向きに対応する
- 不明点は遠慮なく質問する
- 納期に影響する場合は早めに共有する

【トーン】
- プロフェッショナルかつ親しみやすい
- 「お世話になっております」で始める
- 困った時も冷静に解決策を提示
""",
    "delivery": """
あなたはCrowdWorksで受託業務を行うフリーランスです。
納品・検収の段階で、クライアントとやり取りしています。

【対応方針】
- 納品物の内容を明確に説明する
- 検収でのフィードバックには迅速に対応
- 修正は「何をどう直したか」を明記
- 請求・評価のお願いは自然な流れで

【トーン】
- 達成感を共有しつつプロフェッショナル
- 次のステップ（検収・修正・完了）を明確に
""",
    "follow_up": """
あなたはCrowdWorksで受託業務を行うフリーランスです。
案件完了後のフォローアップとして、クライアントとやり取りしています。

【対応方針】
- 感謝を伝える
- 評価のお願いは押しつけがましくなく自然に
- 継続案件・リピートへの関心を示す
- 他に困っていることがないか確認

【トーン】
- 温かく感謝を込めて
- ビジネスライクすぎない
- 長期的な関係構築を意識
""",
}

REPLY_PROMPT = """
以下のCrowdWorksでのメッセージ履歴を読み、最新のクライアントメッセージに対する返信を作成してください。

【案件情報】
案件名: {job_title}
案件URL: {job_url}
案件ステータス: {status}

【メッセージ履歴】（古い順）
{conversation_history}

【返信の条件】
- 100〜300字程度
- 最新のメッセージ内容に正確に応答する
- 会話の流れを踏まえて自然に
- 「ご連絡ありがとうございます」系の定型は毎回使わない
- 具体的なアクションや次のステップを含める
- 不明点があれば質問を含める

返信文のみを出力してください（件名不要）。
"""


def detect_phase(messages, job_status=""):
    """会話内容から案件フェーズを推定"""
    # 直近5メッセージのテキストを結合
    recent_text = " ".join(m["body"] for m in messages[-5:]).lower()
    combined = f"{recent_text} {job_status}".lower()

    scores = {}
    for phase, keywords in PHASE_KEYWORDS.items():
        scores[phase] = sum(1 for kw in keywords if kw.lower() in combined)

    if not any(scores.values()):
        return "pre_contract"

    return max(scores, key=scores.get)


def format_conversation(messages):
    """メッセージ履歴を読みやすい形式に整形"""
    lines = []
    for m in messages:
        sender = "【自分】" if m["is_mine"] else "【クライアント】"
        time_str = f" ({m['time']})" if m.get("time") else ""
        lines.append(f"{sender}{time_str}\n{m['body']}")
    return "\n\n".join(lines)


def generate_reply(thread):
    """スレッド情報から返信文を生成"""
    client = anthropic.Anthropic()

    messages = thread["messages"]
    job_info = thread.get("job_info", {})

    # フェーズ判定
    phase = detect_phase(messages, job_info.get("status", ""))

    system_prompt = PHASE_PROMPTS.get(phase, PHASE_PROMPTS["pre_contract"])
    conversation = format_conversation(messages)

    user_prompt = REPLY_PROMPT.format(
        job_title=job_info.get("job_title", "不明"),
        job_url=job_info.get("job_url", ""),
        status=job_info.get("status", "不明"),
        conversation_history=conversation,
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return {
        "text": message.content[0].text,
        "phase": phase,
    }


if __name__ == "__main__":
    test_thread = {
        "messages": [
            {"sender": "client", "body": "はじめまして。データ入力の件でご応募いただきありがとうございます。いくつか質問があるのですが、対応可能でしょうか？", "time": "3/20 10:00", "is_mine": False},
            {"sender": "me", "body": "ご連絡ありがとうございます。もちろん対応可能です。ご質問をお聞かせください。", "time": "3/20 10:30", "is_mine": True},
            {"sender": "client", "body": "500件のデータのうち、画像のダウンロードとリサイズも含まれるのですが、追加費用はかかりますか？", "time": "3/20 11:00", "is_mine": False},
        ],
        "job_info": {
            "job_title": "ECサイト商品データ入力 500件",
            "job_url": "https://crowdworks.jp/public/jobs/example",
            "status": "応募済み",
        },
    }
    result = generate_reply(test_thread)
    print(f"フェーズ: {result['phase']}")
    print(f"返信文:\n{result['text']}")
