"""
案件収集モジュール — CrowdWorks RSS から案件を取得・フィルタリング
"""

import feedparser
import json
import os
import re
from datetime import datetime, timedelta

# 検索キーワードごとのRSSフィード
SEARCH_KEYWORDS = [
    "データ入力",
    "スクレイピング",
    "Python 自動化",
    "GAS 開発",
    "LP制作",
    "WordPress",
    "業務自動化",
    "Excel VBA",
]

RSS_BASE_URL = "https://crowdworks.jp/public/jobs/search.rss"

# フィルタリング条件
ACCEPT_KEYWORDS = [
    "データ入力", "リスト作成", "転記", "データ整理",
    "スクレイピング", "クローリング", "データ収集",
    "GAS", "Google Apps Script", "スプレッドシート",
    "Python", "自動化", "効率化", "ツール開発",
    "LP", "ランディングページ", "コーディング",
    "WordPress", "ワードプレス", "WP",
    "Excel", "VBA", "マクロ",
    "API", "連携", "Web制作", "HTML", "CSS",
    "商品登録", "ECサイト", "CSV",
]

REJECT_KEYWORDS = [
    "常駐", "出社必須", "フル稼働必須",
    "18禁", "アダルト", "ギャンブル",
    "マルチ", "情報商材",
]

MIN_BUDGET = 0  # 予算フィルタ無効

# 既に通知済みの案件を記録するファイル
SEEN_JOBS_FILE = os.path.join(os.path.dirname(__file__), "seen_jobs.json")


def load_seen_jobs():
    """通知済み案件IDの読み込み"""
    if os.path.exists(SEEN_JOBS_FILE):
        with open(SEEN_JOBS_FILE, "r") as f:
            data = json.load(f)
        # 7日以上前の案件は削除
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        return {k: v for k, v in data.items() if v > cutoff}
    return {}


def save_seen_jobs(seen):
    """通知済み案件IDの保存"""
    with open(SEEN_JOBS_FILE, "w") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def fetch_jobs_for_keyword(keyword):
    """指定キーワードでCrowdWorksのRSSから案件を取得"""
    import urllib.parse
    params = urllib.parse.urlencode({"keyword": keyword})
    url = f"{RSS_BASE_URL}?{params}"

    feed = feedparser.parse(url)
    jobs = []

    for entry in feed.entries:
        job = {
            "id": entry.get("id", entry.link),
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "summary": entry.get("summary", ""),
            "published": entry.get("published", ""),
            "search_keyword": keyword,
        }
        jobs.append(job)

    return jobs


def extract_budget(text):
    """テキストから予算額を抽出"""
    patterns = [
        r"(\d{1,3}(?:,\d{3})*)\s*円",
        r"¥\s*(\d{1,3}(?:,\d{3})*)",
        r"(\d+)\s*万円",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = match.group(1).replace(",", "")
            if "万円" in pattern:
                return int(value) * 10000
            return int(value)
    return None


def passes_filter(job):
    """案件がフィルタ条件を通過するか判定"""
    text = f"{job['title']} {job['summary']}".lower()

    # 拒否キーワードチェック
    for kw in REJECT_KEYWORDS:
        if kw.lower() in text:
            return False

    # 受諾キーワードチェック
    matched = any(kw.lower() in text for kw in ACCEPT_KEYWORDS)
    if not matched:
        return False

    # 予算チェック（予算が読み取れない場合は通す）
    budget = extract_budget(text)
    if budget is not None and budget < MIN_BUDGET:
        return False

    return True


def classify_job(job):
    """案件をカテゴリに分類"""
    text = f"{job['title']} {job['summary']}".lower()

    if any(kw.lower() in text for kw in ["データ入力", "転記", "リスト", "商品登録", "csv", "excel"]):
        return "data_entry"
    if any(kw.lower() in text for kw in ["スクレイピング", "クローリング", "データ収集"]):
        return "scraping"
    if any(kw.lower() in text for kw in ["gas", "google apps script", "スプレッドシート", "vba", "マクロ"]):
        return "automation"
    if any(kw.lower() in text for kw in ["python", "自動化", "ツール開発", "api"]):
        return "development"
    if any(kw.lower() in text for kw in ["lp", "ランディング", "wordpress", "web制作", "html", "コーディング"]):
        return "web_design"
    return "other"


def collect_jobs():
    """全キーワードで案件を収集し、フィルタリング・重複排除して返す"""
    seen = load_seen_jobs()
    all_jobs = []
    seen_ids = set()

    for keyword in SEARCH_KEYWORDS:
        jobs = fetch_jobs_for_keyword(keyword)
        for job in jobs:
            job_id = job["id"]
            if job_id in seen or job_id in seen_ids:
                continue
            if passes_filter(job):
                job["category"] = classify_job(job)
                all_jobs.append(job)
                seen_ids.add(job_id)

    # 通知済みとして記録
    now = datetime.now().isoformat()
    for job in all_jobs:
        seen[job["id"]] = now
    save_seen_jobs(seen)

    return all_jobs


if __name__ == "__main__":
    jobs = collect_jobs()
    print(f"新着案件数: {len(jobs)}")
    for job in jobs:
        print(f"  [{job['category']}] {job['title']}")
        print(f"    URL: {job['url']}")
        print()
