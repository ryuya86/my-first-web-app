"""
CrowdWorks RSS案件収集 — RSSフィードから案件を取得・フィルタリング・JSON出力

Usage:
  python tools/rss_collector.py              → 新着案件をJSON出力
  python tools/rss_collector.py --seen FILE  → seen_jobs.jsonのパスを指定
"""

import feedparser
import json
import os
import re
import sys
import urllib.parse
from datetime import datetime, timedelta

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

SEEN_JOBS_FILE = os.path.join(os.path.dirname(__file__), "..", "state", "seen_jobs.json")


def load_seen_jobs(path=None):
    filepath = path or SEEN_JOBS_FILE
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            data = json.load(f)
        cutoff = (datetime.now() - timedelta(days=7)).isoformat()
        return {k: v for k, v in data.items() if v > cutoff}
    return {}


def save_seen_jobs(seen, path=None):
    filepath = path or SEEN_JOBS_FILE
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2)


def fetch_jobs_for_keyword(keyword):
    params = urllib.parse.urlencode({"keyword": keyword})
    url = f"{RSS_BASE_URL}?{params}"
    feed = feedparser.parse(url)
    jobs = []
    for entry in feed.entries:
        jobs.append({
            "id": entry.get("id", entry.link),
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "summary": entry.get("summary", ""),
            "published": entry.get("published", ""),
            "search_keyword": keyword,
        })
    return jobs


def extract_budget(text):
    patterns = [
        (r"(\d{1,3}(?:,\d{3})*)\s*円", False),
        (r"¥\s*(\d{1,3}(?:,\d{3})*)", False),
        (r"(\d+)\s*万円", True),
    ]
    for pattern, is_man in patterns:
        match = re.search(pattern, text)
        if match:
            value = int(match.group(1).replace(",", ""))
            return value * 10000 if is_man else value
    return None


def passes_filter(job):
    text = f"{job['title']} {job['summary']}".lower()
    if any(kw.lower() in text for kw in REJECT_KEYWORDS):
        return False
    if not any(kw.lower() in text for kw in ACCEPT_KEYWORDS):
        return False
    return True


def classify_job(job):
    text = f"{job['title']} {job['summary']}".lower()
    categories = [
        ("data_entry", ["データ入力", "転記", "リスト", "商品登録", "csv", "excel"]),
        ("scraping", ["スクレイピング", "クローリング", "データ収集"]),
        ("automation", ["gas", "google apps script", "スプレッドシート", "vba", "マクロ"]),
        ("development", ["python", "自動化", "ツール開発", "api"]),
        ("web_design", ["lp", "ランディング", "wordpress", "web制作", "html", "コーディング"]),
    ]
    for cat, keywords in categories:
        if any(kw.lower() in text for kw in keywords):
            return cat
    return "other"


def collect_jobs(seen_path=None):
    seen = load_seen_jobs(seen_path)
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
                budget = extract_budget(f"{job['title']} {job['summary']}")
                job["budget"] = budget
                all_jobs.append(job)
                seen_ids.add(job_id)

    now = datetime.now().isoformat()
    for job in all_jobs:
        seen[job["id"]] = now
    save_seen_jobs(seen, seen_path)

    return all_jobs


if __name__ == "__main__":
    seen_path = None
    if "--seen" in sys.argv:
        idx = sys.argv.index("--seen")
        seen_path = sys.argv[idx + 1]

    jobs = collect_jobs(seen_path)
    print(json.dumps(jobs, ensure_ascii=False, indent=2))
