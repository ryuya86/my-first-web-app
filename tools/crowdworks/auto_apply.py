"""
CrowdWorks自動応募モジュール — Playwrightでブラウザ操作し提案を送信
"""

import asyncio
import json
import os
from playwright.async_api import async_playwright

CROWDWORKS_EMAIL = os.environ.get("CROWDWORKS_EMAIL", "")
CROWDWORKS_PASSWORD = os.environ.get("CROWDWORKS_PASSWORD", "")
LOGIN_URL = "https://crowdworks.jp/login"


async def login(page):
    """CrowdWorksにログイン"""
    await page.goto(LOGIN_URL)
    await page.fill('input[name="username"]', CROWDWORKS_EMAIL)
    await page.fill('input[name="password"]', CROWDWORKS_PASSWORD)
    await page.click('button[type="submit"]')
    await page.wait_for_load_state("networkidle")

    # ログイン成功確認
    if "login" in page.url:
        raise RuntimeError("CrowdWorksログインに失敗しました。認証情報を確認してください。")

    return True


async def submit_proposal(job_url, proposal_text):
    """指定案件に提案文を送信"""
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
            # 1. ログイン
            await login(page)

            # 2. 案件ページへ移動
            await page.goto(job_url)
            await page.wait_for_load_state("networkidle")

            # 3. 「応募画面へ」ボタンをクリック
            apply_button = page.locator('a:has-text("応募画面へ"), a:has-text("この仕事に応募する")')
            if await apply_button.count() == 0:
                raise RuntimeError(f"応募ボタンが見つかりません: {job_url}")
            await apply_button.first.click()
            await page.wait_for_load_state("networkidle")

            # 4. 提案文を入力
            proposal_field = page.locator(
                'textarea[name*="proposal"], '
                'textarea[name*="message"], '
                'textarea[placeholder*="提案"]'
            )
            if await proposal_field.count() == 0:
                raise RuntimeError("提案文入力欄が見つかりません")
            await proposal_field.first.fill(proposal_text)

            # 5. 確認画面へ → 送信
            confirm_button = page.locator(
                'button:has-text("確認"), '
                'input[type="submit"][value*="確認"]'
            )
            if await confirm_button.count() > 0:
                await confirm_button.first.click()
                await page.wait_for_load_state("networkidle")

            submit_button = page.locator(
                'button:has-text("送信"), '
                'button:has-text("応募する"), '
                'input[type="submit"][value*="送信"]'
            )
            if await submit_button.count() > 0:
                await submit_button.first.click()
                await page.wait_for_load_state("networkidle")

            # 6. 完了確認
            success_indicators = [
                page.locator('text="応募が完了しました"'),
                page.locator('text="提案を送信しました"'),
                page.locator('.flash-message--success'),
            ]
            for indicator in success_indicators:
                if await indicator.count() > 0:
                    return {"success": True, "message": "応募完了"}

            # ページタイトルやURLで判断
            if "complete" in page.url or "finish" in page.url:
                return {"success": True, "message": "応募完了（URL確認）"}

            return {
                "success": True,
                "message": "送信処理完了（完了メッセージ未検出のため要確認）",
            }

        except Exception as e:
            # エラー時のスクリーンショット保存
            screenshot_path = "/tmp/crowdworks_error.png"
            await page.screenshot(path=screenshot_path)
            return {
                "success": False,
                "message": str(e),
                "screenshot": screenshot_path,
            }

        finally:
            await browser.close()


def apply_to_job(job_url, proposal_text):
    """同期ラッパー"""
    return asyncio.run(submit_proposal(job_url, proposal_text))


if __name__ == "__main__":
    # テスト実行
    result = apply_to_job(
        "https://crowdworks.jp/public/jobs/example",
        "テスト提案文です。",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
