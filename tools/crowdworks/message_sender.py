"""
CrowdWorksメッセージ送信モジュール — Playwrightでメッセージを返信
"""

import asyncio
from playwright.async_api import async_playwright
import os

CROWDWORKS_EMAIL = os.environ.get("CROWDWORKS_EMAIL", "")
CROWDWORKS_PASSWORD = os.environ.get("CROWDWORKS_PASSWORD", "")
LOGIN_URL = "https://crowdworks.jp/login"


async def _login(page):
    await page.goto(LOGIN_URL)
    await page.fill('input[name="username"]', CROWDWORKS_EMAIL)
    await page.fill('input[name="password"]', CROWDWORKS_PASSWORD)
    await page.click('button[type="submit"]')
    await page.wait_for_load_state("networkidle")
    if "login" in page.url:
        raise RuntimeError("CrowdWorksログイン失敗")


async def _send_message(thread_url, reply_text):
    """指定スレッドにメッセージを送信"""
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
            await page.goto(thread_url)
            await page.wait_for_load_state("networkidle")

            # メッセージ入力欄を検索
            textarea = page.locator(
                'textarea[name*="message"], '
                'textarea[name*="body"], '
                'textarea[placeholder*="メッセージ"], '
                'textarea.message-input, '
                '[contenteditable="true"].message-input'
            )

            if await textarea.count() == 0:
                raise RuntimeError(f"メッセージ入力欄が見つかりません: {thread_url}")

            # contenteditable の場合
            tag = await textarea.first.evaluate("el => el.tagName.toLowerCase()")
            if tag != "textarea":
                await textarea.first.click()
                await page.keyboard.type(reply_text)
            else:
                await textarea.first.fill(reply_text)

            # 送信ボタンをクリック
            send_button = page.locator(
                'button:has-text("送信"), '
                'input[type="submit"][value*="送信"], '
                'button[type="submit"]:has-text("送信"), '
                'button.send-button'
            )

            if await send_button.count() == 0:
                raise RuntimeError("送信ボタンが見つかりません")

            await send_button.first.click()
            await page.wait_for_load_state("networkidle")

            # 送信確認
            # 送信後にエラーが表示されていないか確認
            error_el = page.locator('.error, .alert-danger, [class*="error"]')
            if await error_el.count() > 0:
                error_text = await error_el.first.text_content()
                return {"success": False, "message": f"送信エラー: {error_text}"}

            return {"success": True, "message": "メッセージ送信完了"}

        except Exception as e:
            screenshot_path = "/tmp/crowdworks_msg_error.png"
            await page.screenshot(path=screenshot_path)
            return {
                "success": False,
                "message": str(e),
                "screenshot": screenshot_path,
            }

        finally:
            await browser.close()


def send_reply(thread_url, reply_text):
    """同期ラッパー"""
    return asyncio.run(_send_message(thread_url, reply_text))


if __name__ == "__main__":
    result = send_reply(
        "https://crowdworks.jp/messages/example",
        "テスト送信です。",
    )
    print(result)
