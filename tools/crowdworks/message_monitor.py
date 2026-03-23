"""
CrowdWorksメッセージ監視モジュール — 新着メッセージを取得・構造化
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from smart_selector import smart_find

CROWDWORKS_EMAIL = os.environ.get("CROWDWORKS_EMAIL", "")
CROWDWORKS_PASSWORD = os.environ.get("CROWDWORKS_PASSWORD", "")
LOGIN_URL = "https://crowdworks.jp/login"
MESSAGES_URL = "https://crowdworks.jp/messages"

SEEN_MESSAGES_FILE = os.path.join(os.path.dirname(__file__), "seen_messages.json")


def load_seen_messages():
    if os.path.exists(SEEN_MESSAGES_FILE):
        with open(SEEN_MESSAGES_FILE, "r") as f:
            return json.load(f)
    return {}


def save_seen_messages(seen):
    # 7日以上前のエントリを削除
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    cleaned = {k: v for k, v in seen.items() if v > cutoff}
    with open(SEEN_MESSAGES_FILE, "w") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)


async def _login(page):
    """CrowdWorksにログイン"""
    await page.goto(LOGIN_URL, timeout=30000)
    await page.fill('input[name="username"]', CROWDWORKS_EMAIL)
    await page.fill('input[name="password"]', CROWDWORKS_PASSWORD)
    await page.click('button[type="submit"]')
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(2000)
    if "login" in page.url:
        raise RuntimeError("CrowdWorksログイン失敗")


async def _fetch_thread_list(page):
    """メッセージ一覧からスレッド情報を取得"""
    await page.goto(MESSAGES_URL, timeout=30000)
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(2000)

    threads = await page.evaluate("""
        () => {
            const items = document.querySelectorAll(
                '.message-thread, .message_thread, [class*="thread"], .messages-list li, .message-item'
            );
            return Array.from(items).map(el => {
                const linkEl = el.querySelector('a[href*="/messages/"]');
                const nameEl = el.querySelector(
                    '.user-name, .thread-user, [class*="name"], .sender'
                );
                const previewEl = el.querySelector(
                    '.message-preview, .thread-body, [class*="preview"], .snippet'
                );
                const timeEl = el.querySelector(
                    '.message-time, .thread-time, time, [class*="time"], [class*="date"]'
                );
                const unreadEl = el.querySelector(
                    '.unread, .badge, [class*="unread"], [class*="new"]'
                );
                return {
                    url: linkEl ? linkEl.href : null,
                    client_name: nameEl ? nameEl.textContent.trim() : '',
                    preview: previewEl ? previewEl.textContent.trim() : '',
                    time: timeEl ? timeEl.textContent.trim() : '',
                    has_unread: !!unreadEl,
                };
            }).filter(t => t.url);
        }
    """)

    return threads


async def _fetch_thread_messages(page, thread_url, max_messages=20):
    """個別スレッドのメッセージ履歴を取得"""
    await page.goto(thread_url, timeout=30000)
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(2000)

    messages = await page.evaluate("""
        (max) => {
            const items = document.querySelectorAll(
                '.message, .message-item, [class*="message-body"], .chat-message'
            );
            const result = [];
            const allItems = Array.from(items).slice(-max);
            for (const el of allItems) {
                const senderEl = el.querySelector(
                    '.message-sender, .user-name, [class*="sender"], [class*="name"]'
                );
                const bodyEl = el.querySelector(
                    '.message-body, .message-content, [class*="body"], [class*="content"], p'
                );
                const timeEl = el.querySelector(
                    '.message-time, time, [class*="time"], [class*="date"]'
                );
                const isMine = el.classList.contains('mine') ||
                    el.classList.contains('sent') ||
                    el.getAttribute('data-mine') === 'true';
                result.push({
                    sender: senderEl ? senderEl.textContent.trim() : (isMine ? 'me' : 'client'),
                    body: bodyEl ? bodyEl.textContent.trim() : el.textContent.trim(),
                    time: timeEl ? timeEl.textContent.trim() : '',
                    is_mine: isMine,
                });
            }
            return result;
        }
    """, max_messages)

    # 案件情報を取得（スレッドページに表示されている場合）
    job_info = await page.evaluate("""
        () => {
            const titleEl = document.querySelector(
                '.job-title, [class*="job-title"], .project-title, h2 a[href*="/jobs/"]'
            );
            const statusEl = document.querySelector(
                '.job-status, [class*="status"], .contract-status'
            );
            return {
                job_title: titleEl ? titleEl.textContent.trim() : '',
                job_url: titleEl && titleEl.href ? titleEl.href : '',
                status: statusEl ? statusEl.textContent.trim() : '',
            };
        }
    """)

    return {"messages": messages, "job_info": job_info}


async def fetch_new_messages():
    """未読メッセージのあるスレッドを取得し、会話履歴を構造化"""
    if not CROWDWORKS_EMAIL or not CROWDWORKS_PASSWORD:
        raise RuntimeError("CROWDWORKS_EMAIL / CROWDWORKS_PASSWORD が未設定です")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        try:
            await _login(page)
            threads = await _fetch_thread_list(page)

            seen = load_seen_messages()
            new_threads = []

            for thread in threads:
                if not thread["has_unread"]:
                    continue

                thread_url = thread["url"]
                # スレッドURLからIDを抽出
                thread_id = thread_url.rstrip("/").split("/")[-1]

                # スレッド内メッセージを取得
                thread_data = await _fetch_thread_messages(page, thread_url)

                # 最新メッセージが自分のものならスキップ（返信済み）
                if thread_data["messages"] and thread_data["messages"][-1]["is_mine"]:
                    continue

                # 最新メッセージの内容で重複チェック
                latest_msg = thread_data["messages"][-1]["body"] if thread_data["messages"] else ""
                msg_key = f"{thread_id}:{latest_msg[:100]}"
                if msg_key in seen:
                    continue

                new_threads.append({
                    "thread_id": thread_id,
                    "thread_url": thread_url,
                    "client_name": thread["client_name"],
                    "job_info": thread_data["job_info"],
                    "messages": thread_data["messages"],
                    "latest_message": latest_msg,
                })

                seen[msg_key] = datetime.now().isoformat()

            save_seen_messages(seen)
            return new_threads

        finally:
            await browser.close()


def get_new_messages():
    """同期ラッパー"""
    return asyncio.run(fetch_new_messages())


if __name__ == "__main__":
    threads = get_new_messages()
    print(f"未読スレッド: {len(threads)}件")
    for t in threads:
        print(f"\n--- {t['client_name']} ({t['job_info'].get('job_title', '不明')}) ---")
        for m in t["messages"][-5:]:
            tag = "自分" if m["is_mine"] else "相手"
            print(f"  [{tag}] {m['body'][:80]}")
