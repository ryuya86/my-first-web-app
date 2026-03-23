"""
提案文自動生成モジュール — Claude API を使って案件に最適な提案文を作成
"""

import anthropic
import os

MODEL = "claude-sonnet-4-6"

# カテゴリ別の提案テンプレート指示
CATEGORY_INSTRUCTIONS = {
    "data_entry": """
あなたはクラウドソーシングで案件に応募するフリーランスです。
データ入力・転記系の案件に対する提案文を作成してください。

強調ポイント:
- 正確性（ダブルチェック体制）
- スピード（大量データも対応可能）
- Excel/スプレッドシートの操作スキル
""",
    "scraping": """
あなたはクラウドソーシングで案件に応募するフリーランスです。
スクレイピング・データ収集系の案件に対する提案文を作成してください。

強調ポイント:
- Python/BeautifulSoup/Seleniumの実務経験
- 法的配慮（robots.txt遵守、利用規約確認）
- 構造化データでの納品（CSV/Excel/JSON）
""",
    "automation": """
あなたはクラウドソーシングで案件に応募するフリーランスです。
GAS/VBA/業務自動化系の案件に対する提案文を作成してください。

強調ポイント:
- 業務フローの理解と最適な自動化提案
- GAS/VBA/Pythonでの自動化実績
- 運用しやすいツール設計（マニュアル付き）
""",
    "development": """
あなたはクラウドソーシングで案件に応募するフリーランスです。
Python開発・API連携・ツール開発系の案件に対する提案文を作成してください。

強調ポイント:
- 要件を正確に理解し、最適な技術選定を行う
- テスト・ドキュメント付きの品質
- 段階的な確認で認識齟齬を防止
""",
    "web_design": """
あなたはクラウドソーシングで案件に応募するフリーランスです。
LP制作・WordPress・Web制作系の案件に対する提案文を作成してください。

強調ポイント:
- レスポンシブ対応
- SEO基本設定込み
- デザインカンプからの忠実なコーディング
""",
    "other": """
あなたはクラウドソーシングで案件に応募するフリーランスです。
案件内容をよく読み、適切な提案文を作成してください。

強調ポイント:
- 案件内容の的確な理解
- 対応可能な根拠
- 丁寧なコミュニケーション
""",
}

COMMON_PROMPT = """
【案件情報】
タイトル: {title}
詳細: {summary}
URL: {url}

【提案文の条件】
- 300〜500字
- 丁寧だが簡潔なトーン
- 以下の構成で:
  1. 挨拶（1行）
  2. 案件内容の理解を示す（2〜3行）
  3. 対応可能な理由・スキル（3〜4行）
  4. 進め方の提案（3〜4行）
  5. 納期・稼働の目安（1〜2行）
  6. 締め（1行）
- テンプレート感を出さず、案件固有の内容に触れる
- 「ご依頼内容を拝見し」から始める
"""


def generate_proposal(job):
    """案件情報から提案文を生成"""
    client = anthropic.Anthropic()

    category = job.get("category", "other")
    system_prompt = CATEGORY_INSTRUCTIONS.get(category, CATEGORY_INSTRUCTIONS["other"])

    user_prompt = COMMON_PROMPT.format(
        title=job["title"],
        summary=job["summary"],
        url=job["url"],
    )

    message = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return message.content[0].text


if __name__ == "__main__":
    # テスト用
    test_job = {
        "title": "【データ入力】ECサイトの商品情報を500件登録してほしい",
        "summary": "Shopifyの管理画面から商品情報（商品名、価格、説明文、画像URL）を登録する作業です。CSVでのインポートも可。予算5万円。",
        "url": "https://crowdworks.jp/public/jobs/example",
        "category": "data_entry",
    }
    proposal = generate_proposal(test_job)
    print("=== 生成された提案文 ===")
    print(proposal)
