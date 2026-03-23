"""
クライアント評価スクリーニング — クライアントの信頼度を事前チェック
"""

import asyncio
from dataclasses import dataclass
from playwright.async_api import async_playwright


@dataclass
class ClientProfile:
    name: str
    rating: float           # 総合評価 (0-5)
    total_jobs: int          # 発注実績
    total_paid: str          # 総支払額
    response_rate: str       # 返信率
    verification: list       # 本人確認状況
    member_since: str        # 登録日
    trust_score: int         # 信頼スコア (0-100)
    warnings: list           # 警告事項
    recommendation: str      # "safe" | "caution" | "danger"


TRUST_RULES = [
    {"condition": lambda p: p["rating"] < 3.0 and p["total_jobs"] > 0,
     "warning": "低評価（{rating}）", "penalty": 30},
    {"condition": lambda p: p["total_jobs"] == 0,
     "warning": "発注実績なし（新規クライアント）", "penalty": 15},
    {"condition": lambda p: p["total_jobs"] < 3,
     "warning": "発注実績が少ない（{total_jobs}件）", "penalty": 10},
    {"condition": lambda p: "本人確認" not in " ".join(p.get("verification", [])),
     "warning": "本人確認未済", "penalty": 20},
    {"condition": lambda p: p.get("response_rate_num", 100) < 50,
     "warning": "返信率が低い（{response_rate}）", "penalty": 15},
]


async def _scrape_client_profile(client_url: str) -> dict:
    """クライアントプロフィールページをスクレイピング"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        try:
            await page.goto(client_url, wait_until="networkidle")

            profile = await page.evaluate("""
                () => {
                    const getText = (sel) => {
                        const el = document.querySelector(sel);
                        return el ? el.textContent.trim() : '';
                    };
                    const getAll = (sel) => {
                        return Array.from(document.querySelectorAll(sel))
                            .map(el => el.textContent.trim());
                    };

                    const ratingEl = document.querySelector(
                        '.rating, [class*="rating"], .star-rating, [class*="score"]'
                    );
                    const ratingText = ratingEl ? ratingEl.textContent.trim() : '0';
                    const ratingMatch = ratingText.match(/(\\d+\\.?\\d*)/);

                    const jobCountEl = document.querySelector(
                        '[class*="job-count"], [class*="order"], .total-jobs'
                    );
                    const jobText = jobCountEl ? jobCountEl.textContent.trim() : '0';
                    const jobMatch = jobText.match(/(\\d+)/);

                    return {
                        name: getText('.user-name, .client-name, h1, [class*="name"]'),
                        rating: ratingMatch ? parseFloat(ratingMatch[1]) : 0,
                        total_jobs: jobMatch ? parseInt(jobMatch[1]) : 0,
                        total_paid: getText('[class*="paid"], [class*="payment"]'),
                        response_rate: getText('[class*="response"], [class*="reply"]'),
                        verification: getAll('[class*="verify"], [class*="badge"], .verification'),
                        member_since: getText('[class*="since"], [class*="registered"], .join-date'),
                    };
                }
            """)

            return profile

        finally:
            await browser.close()


def calculate_trust_score(profile: dict) -> ClientProfile:
    """プロフィール情報から信頼スコアを算出"""
    score = 100
    warnings = []

    # 返信率を数値化
    response_str = profile.get("response_rate", "")
    rate_match = None
    import re
    rate_match = re.search(r"(\d+)", response_str)
    profile["response_rate_num"] = int(rate_match.group(1)) if rate_match else 100

    for rule in TRUST_RULES:
        try:
            if rule["condition"](profile):
                warning = rule["warning"].format(**profile)
                warnings.append(warning)
                score -= rule["penalty"]
        except (KeyError, TypeError):
            continue

    score = max(0, min(100, score))

    if score >= 70:
        recommendation = "safe"
    elif score >= 40:
        recommendation = "caution"
    else:
        recommendation = "danger"

    return ClientProfile(
        name=profile.get("name", "不明"),
        rating=profile.get("rating", 0),
        total_jobs=profile.get("total_jobs", 0),
        total_paid=profile.get("total_paid", ""),
        response_rate=profile.get("response_rate", ""),
        verification=profile.get("verification", []),
        member_since=profile.get("member_since", ""),
        trust_score=score,
        warnings=warnings,
        recommendation=recommendation,
    )


async def screen_client(client_url: str) -> ClientProfile:
    """クライアントをスクリーニング"""
    profile = await _scrape_client_profile(client_url)
    return calculate_trust_score(profile)


def screen_client_sync(client_url: str) -> ClientProfile:
    """同期ラッパー"""
    return asyncio.run(screen_client(client_url))


def format_screening_for_slack(cp: ClientProfile) -> str:
    """Slack表示用にフォーマット"""
    icons = {"safe": "🟢", "caution": "🟡", "danger": "🔴"}
    icon = icons.get(cp.recommendation, "⚪")
    labels = {"safe": "安全", "caution": "注意", "danger": "危険"}

    lines = [
        f"{icon} *クライアント信頼度: {cp.trust_score}点 ({labels[cp.recommendation]})*",
        f"  評価: {'⭐' * int(cp.rating)}{cp.rating} | 発注: {cp.total_jobs}件",
    ]

    if cp.warnings:
        lines.append("  ⚠️ " + " / ".join(cp.warnings))

    return "\n".join(lines)


if __name__ == "__main__":
    # ローカルテスト（プロフィールデータを直接指定）
    test_profile = {
        "name": "テスト太郎",
        "rating": 4.5,
        "total_jobs": 25,
        "total_paid": "500,000円",
        "response_rate": "90%",
        "verification": ["本人確認済み"],
        "member_since": "2020年1月",
    }
    result = calculate_trust_score(test_profile)
    print(f"信頼スコア: {result.trust_score}")
    print(f"推奨: {result.recommendation}")
    print(f"警告: {result.warnings}")
