"""
返信テンプレートライブラリ — よく使うパターンをDB管理し、AI生成の参考に注入
"""

import json
import os
import sqlite3
from contextlib import contextmanager

TEMPLATES_DB = os.path.join(os.path.dirname(__file__), "crowdworks_history.db")

# デフォルトテンプレート
DEFAULT_TEMPLATES = [
    # 受注前
    {
        "phase": "pre_contract",
        "scenario": "初回挨拶・自己紹介",
        "template": (
            "はじめまして、ご連絡ありがとうございます。\n"
            "ご依頼内容を拝見いたしました。{job_title}について、"
            "私の経験を活かしてお力になれると考えております。\n"
            "いくつか確認させていただきたい点がございますので、"
            "よろしければお聞かせいただけますでしょうか。"
        ),
        "tags": "挨拶,初回,自己紹介",
    },
    {
        "phase": "pre_contract",
        "scenario": "見積り・納期回答",
        "template": (
            "ご質問ありがとうございます。\n"
            "ご依頼内容を確認させていただいたところ、"
            "お見積りは{budget_range}程度、納期は{deadline}を想定しております。\n"
            "詳細な仕様によって変動する可能性がございますので、"
            "もう少し具体的なご要件をお聞かせいただけますと、"
            "正確なお見積りをご提示できます。"
        ),
        "tags": "見積,納期,価格",
    },
    {
        "phase": "pre_contract",
        "scenario": "追加要件への対応",
        "template": (
            "追加のご要件について承知いたしました。\n"
            "{additional_scope}につきましても対応可能です。\n"
            "スコープが広がりますので、"
            "追加分として{additional_cost}程度のお見積りとなります。\n"
            "ご検討いただけますでしょうか。"
        ),
        "tags": "追加,スコープ,変更",
    },
    # 進行中
    {
        "phase": "in_progress",
        "scenario": "進捗報告",
        "template": (
            "お世話になっております。進捗をご報告いたします。\n\n"
            "【進捗状況】\n"
            "- 完了: {completed_items}\n"
            "- 進行中: {current_items}\n"
            "- 残り: {remaining_items}\n\n"
            "予定通り{deadline}までに完了見込みです。\n"
            "途中経過のファイルを添付いたしますので、ご確認ください。"
        ),
        "tags": "進捗,報告,中間",
    },
    {
        "phase": "in_progress",
        "scenario": "修正依頼への対応",
        "template": (
            "修正のご指示ありがとうございます。\n"
            "ご指摘いただいた{modification_points}点について、"
            "修正対応いたします。\n"
            "{estimated_time}以内に修正版をお送りいたしますので、"
            "少々お待ちください。"
        ),
        "tags": "修正,フィードバック,対応",
    },
    {
        "phase": "in_progress",
        "scenario": "不明点の確認",
        "template": (
            "お世話になっております。作業を進める中で、"
            "いくつか確認させていただきたい点がございます。\n\n"
            "{questions}\n\n"
            "お手数ですが、ご回答いただけますと幸いです。\n"
            "上記以外の部分は引き続き作業を進めてまいります。"
        ),
        "tags": "質問,確認,不明点",
    },
    # 納品
    {
        "phase": "delivery",
        "scenario": "納品連絡",
        "template": (
            "お世話になっております。作業が完了いたしましたので、"
            "納品物をお送りいたします。\n\n"
            "【納品内容】\n{deliverables}\n\n"
            "ご確認いただき、修正点等ございましたら"
            "お気軽にお申し付けください。\n"
            "問題なければ検収のご承認をお願いいたします。"
        ),
        "tags": "納品,完了,検収",
    },
    {
        "phase": "delivery",
        "scenario": "検収後の修正対応",
        "template": (
            "検収のご確認ありがとうございます。\n"
            "ご指摘の{modification_count}点について修正いたしました。\n\n"
            "【修正内容】\n{modifications}\n\n"
            "再度ご確認をお願いいたします。"
        ),
        "tags": "検収,修正,再納品",
    },
    # フォローアップ
    {
        "phase": "follow_up",
        "scenario": "完了のお礼・評価依頼",
        "template": (
            "この度はご依頼いただきありがとうございました。\n"
            "無事に完了できてうれしく思います。\n\n"
            "お手すきの際に、評価をいただけますと大変ありがたいです。\n"
            "今後も同様の案件がございましたら、"
            "ぜひお声がけください。引き続きよろしくお願いいたします。"
        ),
        "tags": "お礼,評価,フォロー",
    },
    {
        "phase": "follow_up",
        "scenario": "リピート提案",
        "template": (
            "ご連絡ありがとうございます。\n"
            "前回のお仕事では大変お世話になりました。\n\n"
            "今回のご依頼についても喜んでお受けいたします。\n"
            "前回の経験を活かして、よりスムーズに対応できるかと思います。\n"
            "詳細をお聞かせいただけますでしょうか。"
        ),
        "tags": "リピート,継続,再依頼",
    },
]


def init_templates_table():
    """テンプレートテーブルを初期化"""
    conn = sqlite3.connect(TEMPLATES_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reply_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phase TEXT NOT NULL,
            scenario TEXT NOT NULL,
            template TEXT NOT NULL,
            tags TEXT,
            use_count INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(phase, scenario)
        )
    """)

    # デフォルトテンプレートを挿入
    for t in DEFAULT_TEMPLATES:
        conn.execute("""
            INSERT OR IGNORE INTO reply_templates (phase, scenario, template, tags)
            VALUES (?, ?, ?, ?)
        """, (t["phase"], t["scenario"], t["template"], t["tags"]))

    conn.commit()
    conn.close()


def get_templates_for_phase(phase: str) -> list[dict]:
    """指定フェーズのテンプレート一覧を取得"""
    conn = sqlite3.connect(TEMPLATES_DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM reply_templates WHERE phase = ? ORDER BY use_count DESC",
        (phase,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_best_template(phase: str, message_text: str) -> dict | None:
    """メッセージ内容に最もマッチするテンプレートを取得"""
    templates = get_templates_for_phase(phase)
    if not templates:
        return None

    # タグベースの簡易マッチング
    best = None
    best_score = 0

    for t in templates:
        tags = [tag.strip() for tag in (t.get("tags") or "").split(",") if tag.strip()]
        score = sum(1 for tag in tags if tag in message_text)

        # 使用回数ボーナス
        score += min(t.get("use_count", 0) * 0.1, 2)

        if score > best_score:
            best_score = score
            best = t

    return best


def increment_use_count(template_id: int):
    """テンプレートの使用回数をインクリメント"""
    conn = sqlite3.connect(TEMPLATES_DB)
    conn.execute(
        "UPDATE reply_templates SET use_count = use_count + 1 WHERE id = ?",
        (template_id,),
    )
    conn.commit()
    conn.close()


def format_templates_for_prompt(phase: str, message_text: str) -> str:
    """AI返信生成プロンプトに注入するテンプレート情報"""
    templates = get_templates_for_phase(phase)
    if not templates:
        return ""

    best = get_best_template(phase, message_text)

    lines = ["\n【参考テンプレート】以下のテンプレートのトーンと構成を参考にしてください:\n"]

    if best:
        lines.append(f"最も関連性の高いテンプレート（{best['scenario']}）:")
        lines.append(f"```\n{best['template']}\n```\n")

    # 他のテンプレートのシナリオ名だけ列挙
    others = [t for t in templates if t != best][:3]
    if others:
        lines.append("その他の利用可能なシナリオ: " + ", ".join(t["scenario"] for t in others))

    return "\n".join(lines)


# 初期化
init_templates_table()


if __name__ == "__main__":
    templates = get_templates_for_phase("pre_contract")
    print(f"契約前テンプレート: {len(templates)}件")
    for t in templates:
        print(f"  - {t['scenario']}")

    prompt_addition = format_templates_for_prompt(
        "pre_contract",
        "見積りと納期を教えてください",
    )
    print(f"\nプロンプト追加:\n{prompt_addition}")
