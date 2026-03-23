"""
CrowdWorks案件収集 — 検索ページのJSON埋め込みデータから案件を取得・フィルタリング

Usage:
  python tools/rss_collector.py              → 新着案件をJSON出力
  python tools/rss_collector.py --seen FILE  → seen_jobs.jsonのパスを指定
"""

import html as htmlmod
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

SEARCH_KEYWORDS = [
    # コアスキル（ポートフォリオ直結）
    "GAS 開発",
    "Google Apps Script",
    "スクレイピング",
    "Python 自動化",
    "Slack bot",
    "API連携",
    "Gmail API",
    # AIで自動化しやすい業務
    "データ入力",
    "商品登録",
    "リスト作成",
    "CSV作成",
    "データ抽出",
    "PDF処理",
    "請求書作成",
    "メール自動送信",
    # 関連スキル
    "スプレッドシート 自動化",
    "業務自動化",
    "Excel VBA",
    "ツール開発",
    # Web系
    "LP制作",
    "WordPress",
]

SEARCH_BASE_URL = "https://crowdworks.jp/public/jobs"

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
    # 地理的制約
    "在住の方", "在住者", "在住限定",
    "カナダ在住", "香港在住", "アメリカ在住", "海外在住",
    "韓国在住", "中国在住", "台湾在住",
    # 低単価タスク
    "アンケート", "モニター", "レビュー投稿", "体験談",
    "口コミ", "感想文",
]

# 報酬が低すぎるタスク案件を除外する閾値
MIN_BUDGET_THRESHOLD = 1000  # 1,000円未満は除外

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

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
    """検索ページのHTML埋め込みJSONから案件を取得"""
    url = f"{SEARCH_BASE_URL}?keyword={urllib.parse.quote(keyword)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    try:
        raw = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")
    except Exception as e:
        print(f"  [WARN] {keyword}: 取得失敗 ({e})", file=sys.stderr)
        return []

    decoded = htmlmod.unescape(raw)

    match = re.search(r'"job_offers":(\[.*?\]),"pr_diamond"', decoded, re.DOTALL)
    if not match:
        match = re.search(r'"job_offers":(\[.*?\]),"pr_', decoded, re.DOTALL)
    if not match:
        print(f"  [WARN] {keyword}: JSON抽出失敗", file=sys.stderr)
        return []

    try:
        raw_jobs = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        print(f"  [WARN] {keyword}: JSONパース失敗 ({e})", file=sys.stderr)
        return []

    jobs = []
    for item in raw_jobs:
        jo = item.get("job_offer", {})
        payment = item.get("payment", {})
        entry = item.get("entry", {}).get("project_entry", {})

        # 報酬情報を抽出
        budget_min = None
        budget_max = None
        if "fixed_price_payment" in payment:
            fp = payment["fixed_price_payment"]
            budget_min = fp.get("min_budget")
            budget_max = fp.get("max_budget")
        elif "hourly_payment" in payment:
            hp = payment["hourly_payment"]
            budget_min = hp.get("min_hourly_wage")
            budget_max = hp.get("max_hourly_wage")

        jobs.append({
            "id": str(jo.get("id", "")),
            "title": jo.get("title", ""),
            "url": f"https://crowdworks.jp/public/jobs/{jo.get('id', '')}",
            "summary": jo.get("description_digest", ""),
            "published": jo.get("last_released_at", ""),
            "expired_on": jo.get("expired_on", ""),
            "search_keyword": keyword,
            "budget_min": budget_min,
            "budget_max": budget_max,
            "num_applications": entry.get("num_application_conditions", 0),
        })

    return jobs


def passes_filter(job):
    text = f"{job['title']} {job['summary']}".lower()
    # REJECTキーワードに該当する場合は除外
    if any(kw.lower() in text for kw in REJECT_KEYWORDS):
        return False
    # 低単価タスク除外（max_budgetが設定されていて閾値未満）
    max_budget = job.get("budget_max")
    if max_budget is not None and 0 < max_budget < MIN_BUDGET_THRESHOLD:
        return False
    # 検索キーワードで既にマッチしているため、ACCEPTフィルタは不要
    # （スコアリングでスキルマッチを評価する）
    return True


def classify_job(job):
    text = f"{job['title']} {job['summary']}".lower()
    categories = [
        ("scraping", ["スクレイピング", "クローリング", "データ抽出", "データ収集"]),
        ("automation", ["gas", "google apps script", "スプレッドシート", "vba", "マクロ", "自動化", "rpa"]),
        ("development", ["python", "ツール開発", "api", "bot", "webhook"]),
        ("data_entry", ["データ入力", "転記", "リスト", "商品登録", "csv", "excel"]),
        ("document", ["pdf", "請求書", "書類作成", "テンプレート", "メール作成"]),
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

    for i, keyword in enumerate(SEARCH_KEYWORDS):
        jobs = fetch_jobs_for_keyword(keyword)
        for job in jobs:
            job_id = job["id"]
            if job_id in seen or job_id in seen_ids:
                continue
            if passes_filter(job):
                job["category"] = classify_job(job)
                all_jobs.append(job)
                seen_ids.add(job_id)

        # レート制限対策
        if i < len(SEARCH_KEYWORDS) - 1:
            time.sleep(1)

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
