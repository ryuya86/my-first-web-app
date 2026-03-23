"""
競合応募者数モニタリング — 案件の応募人数を取得し、競争率で優先度付け
"""

import asyncio
import re
from playwright.async_api import async_playwright


async def _fetch_applicant_count(page, job_url: str) -> dict:
    """案件ページから応募者数を取得"""
    try:
        await page.goto(job_url, timeout=30000)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(2000)

        data = await page.evaluate("""
            () => {
                const getText = (sel) => {
                    const el = document.querySelector(sel);
                    return el ? el.textContent.trim() : '';
                };

                return {
                    applicant_text: getText(
                        '[class*="applicant"], [class*="apply-count"], '
                        + '[class*="proposal-count"], .entry-count'
                    ),
                    deadline_text: getText(
                        '[class*="deadline"], [class*="expire"], [class*="end-date"]'
                    ),
                    page_text: document.body ? document.body.innerText.substring(0, 3000) : '',
                };
            }
        """)

        # 応募者数を抽出
        applicant_count = 0
        patterns = [
            r"応募(?:者)?(?:数)?[\s:：]*(\d+)",
            r"(\d+)\s*(?:人|名)(?:が)?応募",
            r"提案[\s:：]*(\d+)",
            r"(\d+)\s*(?:件)?(?:の)?提案",
        ]
        combined_text = f"{data['applicant_text']} {data['page_text']}"
        for pattern in patterns:
            match = re.search(pattern, combined_text)
            if match:
                applicant_count = int(match.group(1))
                break

        return {
            "url": job_url,
            "applicant_count": applicant_count,
            "deadline": data["deadline_text"],
        }

    except Exception as e:
        return {
            "url": job_url,
            "applicant_count": -1,
            "error": str(e),
        }


async def fetch_competitor_counts(job_urls: list[str]) -> list[dict]:
    """複数案件の応募者数を一括取得"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        results = []
        try:
            for url in job_urls:
                result = await _fetch_applicant_count(page, url)
                results.append(result)
        finally:
            await browser.close()

        return results


def get_competitor_counts(job_urls: list[str]) -> list[dict]:
    """同期ラッパー"""
    return asyncio.run(fetch_competitor_counts(job_urls))


def prioritize_by_competition(jobs: list) -> list:
    """競合応募者数で案件を優先度付け"""
    urls = [j.get("url", "") for j in jobs if j.get("url")]

    if not urls:
        return jobs

    counts = get_competitor_counts(urls)
    count_map = {c["url"]: c["applicant_count"] for c in counts}

    for job in jobs:
        job["competitor_count"] = count_map.get(job.get("url", ""), -1)

    # 応募者数が少ない順にソート（-1は不明なので末尾）
    jobs.sort(key=lambda j: (
        j.get("competitor_count", 999) if j.get("competitor_count", -1) >= 0 else 999
    ))

    return jobs


def format_competition_for_slack(job: dict) -> str:
    """Slack表示用に競争率をフォーマット"""
    count = job.get("competitor_count", -1)

    if count < 0:
        return "👥 応募者数: 不明"

    if count <= 5:
        icon = "🟢"
        label = "競争率低"
    elif count <= 15:
        icon = "🟡"
        label = "競争率中"
    else:
        icon = "🔴"
        label = "競争率高"

    return f"{icon} 応募者: {count}人 ({label})"


if __name__ == "__main__":
    test_jobs = [
        {"url": "https://crowdworks.jp/public/jobs/example1", "title": "テスト案件1"},
        {"url": "https://crowdworks.jp/public/jobs/example2", "title": "テスト案件2"},
    ]
    print("競合モニタリングテスト（実際のURLでは動作します）")
