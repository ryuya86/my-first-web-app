"""
NGワード・禁止表現チェッカー — 送信前にテキストの安全性を検証

Usage:
  python tools/ng_checker.py "チェックしたいテキスト"
  → 安全ならexit 0、NGならexit 1 + 違反内容を出力
"""

import json
import re
import sys

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
        ],
    },
    "confidentiality_leak": {
        "label": "機密情報漏洩リスク",
        "severity": "error",
        "patterns": [
            r"他の?(?:クライアント|お客様|案件).*(?:情報|内容|詳細)",
            r"(?:以前|過去)の(?:クライアント|お客様).*(?:教え|お伝え|共有)",
        ],
    },
    "external_redirect": {
        "label": "外部誘導（CrowdWorks規約違反）",
        "severity": "error",
        "patterns": [
            r"(?:直接|個別|外部)(?:で|に)?(?:やり取り|取引|連絡|契約)",
            r"(?:CrowdWorks|クラウドワークス)(?:を|は)?(?:通さず|介さず|外で)",
            r"(?:手数料|システム利用料).*(?:節約|かからない|省ける)",
        ],
    },
    "personal_info": {
        "label": "個人情報の記載",
        "severity": "error",
        "patterns": [
            r"\d{2,4}-\d{2,4}-\d{3,4}",
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}",
            r"(?:携帯|電話|TEL|tel)[\s:：]?\d",
            r"(?:LINE|ライン)[\s]*(?:ID|アイディー)[\s:：]",
        ],
    },
    "overpromise": {
        "label": "過剰な約束",
        "severity": "warning",
        "patterns": [
            r"(?:どんな|いかなる|あらゆる).*(?:対応|可能|できます)",
            r"24時間.*(?:対応|サポート|返信)",
        ],
    },
}


def check_text(text):
    violations = []
    for category, config in NG_PATTERNS.items():
        for pattern in config["patterns"]:
            for match in re.finditer(pattern, text):
                violations.append({
                    "category": category,
                    "label": config["label"],
                    "matched": match.group(),
                    "severity": config["severity"],
                })
    return violations


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/ng_checker.py 'テキスト'")
        sys.exit(1)

    text = sys.argv[1]
    violations = check_text(text)

    if not violations:
        print("✅ NGワードなし")
        sys.exit(0)

    has_errors = any(v["severity"] == "error" for v in violations)
    for v in violations:
        icon = "🚫" if v["severity"] == "error" else "⚠️"
        print(f"{icon} {v['label']}: {v['matched']}")

    print(json.dumps(violations, ensure_ascii=False))
    sys.exit(1 if has_errors else 0)
