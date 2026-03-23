"""
NGワード・禁止表現チェッカー — AI返信文の安全性を送信前に検証
"""

import re
from dataclasses import dataclass


@dataclass
class NGCheckResult:
    is_safe: bool
    violations: list  # [{"category": str, "matched": str, "severity": "error"|"warning"}]
    sanitized_text: str  # warning のみの場合、修正候補テキスト


# カテゴリ別NGワードパターン
NG_PATTERNS = {
    "price_commitment": {
        "label": "価格確約表現",
        "severity": "error",
        "patterns": [
            r"(?:必ず|絶対に?|確実に)\d+[万円]",
            r"(?:最低|最高)でも?\d+[万円]",
            r"\d+[万円](?:で(?:やります|お受けします|対応します|引き受けます))",
            r"(?:値下げ|割引|無料)(?:します|いたします|可能です)",
            r"追加料金(?:は|が)?(?:一切|絶対)?(?:かかりません|不要|ありません|なし)",
        ],
    },
    "deadline_guarantee": {
        "label": "納期保証表現",
        "severity": "error",
        "patterns": [
            r"(?:必ず|絶対に?|確実に)(?:間に合|納品|完了|お届け)",
            r"100%.*(?:納期|期日|期限).*(?:守|間に合)",
            r"(?:遅延|遅れ)(?:は|が)?(?:一切|絶対)?(?:ありません|ございません|しません)",
        ],
    },
    "legal_commitment": {
        "label": "法的拘束力のある約束",
        "severity": "error",
        "patterns": [
            r"(?:損害|賠償|補償).*(?:します|いたします|保証)",
            r"(?:無制限|無限)(?:の|に)?(?:修正|対応|サポート)",
            r"(?:返金|全額返金).*(?:保証|約束|確約)",
            r"(?:契約|合意)(?:書|内容)?(?:に関わらず|を超えて)",
        ],
    },
    "confidentiality_leak": {
        "label": "機密情報漏洩リスク",
        "severity": "error",
        "patterns": [
            r"他の?(?:クライアント|お客様|案件).*(?:情報|内容|詳細)",
            r"(?:以前|過去)の(?:クライアント|お客様).*(?:教え|お伝え|共有)",
            r"(?:社外秘|機密|非公開).*(?:見せ|お見せ|共有|教え)",
        ],
    },
    "competitor_mention": {
        "label": "競合サービスへの言及",
        "severity": "warning",
        "patterns": [
            r"(?:ランサーズ|ココナラ|Fiverr|Upwork)(?:で|では|の方が|なら)",
        ],
    },
    "negative_expression": {
        "label": "ネガティブ表現",
        "severity": "warning",
        "patterns": [
            r"(?:できません|無理です|対応できません|不可能)",
            r"(?:わかりません|知りません|存じません)",
            r"(?:難しい|厳しい)(?:です|と思います|かと)",
        ],
    },
    "overpromise": {
        "label": "過剰な約束",
        "severity": "warning",
        "patterns": [
            r"(?:どんな|いかなる|あらゆる).*(?:対応|可能|できます)",
            r"24時間.*(?:対応|サポート|返信)",
            r"(?:即日|即座|即時).*(?:対応|完了|納品)",
        ],
    },
    "personal_info": {
        "label": "個人情報の記載",
        "severity": "error",
        "patterns": [
            r"\d{2,4}-\d{2,4}-\d{3,4}",  # 電話番号
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",  # メールアドレス
            r"(?:携帯|電話|TEL|tel)[\s:：]?\d",
            r"(?:LINE|ライン)[\s]*(?:ID|アイディー)[\s:：]",
        ],
    },
}

# CrowdWorks利用規約で禁止される外部誘導表現
EXTERNAL_REDIRECT_PATTERNS = {
    "label": "外部誘導（CrowdWorks規約違反）",
    "severity": "error",
    "patterns": [
        r"(?:直接|個別|外部)(?:で|に)?(?:やり取り|取引|連絡|契約)",
        r"(?:CrowdWorks|クラウドワークス)(?:を|は)?(?:通さず|介さず|外で)",
        r"(?:手数料|システム利用料).*(?:節約|かからない|省ける)",
    ],
}
NG_PATTERNS["external_redirect"] = EXTERNAL_REDIRECT_PATTERNS


def check_ng_words(text: str) -> NGCheckResult:
    """テキストのNGワードチェックを実行"""
    violations = []

    for category, config in NG_PATTERNS.items():
        for pattern in config["patterns"]:
            matches = re.finditer(pattern, text)
            for match in matches:
                violations.append({
                    "category": category,
                    "label": config["label"],
                    "matched": match.group(),
                    "position": match.start(),
                    "severity": config["severity"],
                })

    has_errors = any(v["severity"] == "error" for v in violations)
    is_safe = len(violations) == 0

    # warning のみの場合、該当箇所をハイライトした参考テキストを生成
    sanitized = text
    if violations and not has_errors:
        for v in sorted(violations, key=lambda x: x["position"], reverse=True):
            pos = v["position"]
            matched = v["matched"]
            sanitized = (
                sanitized[:pos]
                + f"【⚠️ {v['label']}】{matched}"
                + sanitized[pos + len(matched):]
            )

    return NGCheckResult(
        is_safe=is_safe,
        violations=violations,
        sanitized_text=sanitized,
    )


def format_violations_for_slack(result: NGCheckResult) -> str:
    """Slack表示用にviolationsをフォーマット"""
    if result.is_safe:
        return ""

    lines = ["*⚠️ NGワードチェック結果:*\n"]
    for v in result.violations:
        icon = "🚫" if v["severity"] == "error" else "⚠️"
        lines.append(f"{icon} *{v['label']}*: `{v['matched']}`")

    errors = sum(1 for v in result.violations if v["severity"] == "error")
    warnings = sum(1 for v in result.violations if v["severity"] == "warning")

    if errors:
        lines.append(f"\n🚫 エラー {errors}件 — *送信をブロックしました*")
    if warnings:
        lines.append(f"⚠️ 警告 {warnings}件 — 確認を推奨")

    return "\n".join(lines)


if __name__ == "__main__":
    test_texts = [
        "お世話になっております。納期については必ず間に合わせます。追加料金は一切かかりません。",
        "ご確認ありがとうございます。修正は2日程度で対応可能です。",
        "直接やり取りした方が手数料もかからないのでメールで連絡しませんか？",
        "24時間対応可能です。どんな修正でもお受けします。",
    ]

    for text in test_texts:
        result = check_ng_words(text)
        print(f"\n入力: {text[:60]}...")
        print(f"  安全: {result.is_safe}")
        for v in result.violations:
            print(f"  {v['severity']}: [{v['label']}] {v['matched']}")
