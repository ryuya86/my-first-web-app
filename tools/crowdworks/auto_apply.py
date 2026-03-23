"""
CrowdWorks自動応募モジュール — Playwrightでブラウザ操作し提案を送信
"""

import asyncio
import json
import os
from playwright.async_api import async_playwright
from smart_selector import smart_find

CROWDWORKS_EMAIL = os.environ.get("CROWDWORKS_EMAIL", "")
CROWDWORKS_PASSWORD = os.environ.get("CROWDWORKS_PASSWORD", "")
LOGIN_URL = "https://crowdworks.jp/login"


async def login(page):
    """CrowdWorksにログイン"""
    await page.goto(LOGIN_URL, timeout=30000)
    await page.fill('input[name="username"]', CROWDWORKS_EMAIL)
    await page.fill('input[name="password"]', CROWDWORKS_PASSWORD)
    await page.click('button[type="submit"]')
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(2000)

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
            await page.goto(job_url, timeout=30000)
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)

            # 3. 「応募画面へ」ボタンをクリック（AI fallback付き）
            apply_button = await smart_find(page, [
                'a:has-text("応募画面へ")',
                'a:has-text("この仕事に応募する")',
                'a:has-text("応募する")',
                'button:has-text("応募")',
            ], purpose="案件への応募ボタン")
            if not apply_button:
                raise RuntimeError(f"応募ボタンが見つかりません: {job_url}")
            await apply_button.click()
            await page.wait_for_load_state("domcontentloaded")
            await page.wait_for_timeout(2000)

            # 4. 提案文を入力（AI fallback付き）
            proposal_field = await smart_find(page, [
                'textarea[name*="proposal"]',
                'textarea[name*="message"]',
                'textarea[placeholder*="提案"]',
                'textarea[placeholder*="メッセージ"]',
                'textarea',
            ], purpose="提案文・メッセージ入力欄（textarea）")
            if not proposal_field:
                raise RuntimeError("提案文入力欄が見つかりません")
            await proposal_field.fill(proposal_text)

            # 5. 確認画面へ → 送信（AI fallback付き）
            confirm_button = await smart_find(page, [
                'button:has-text("確認")',
                'input[type="submit"][value*="確認"]',
            ], purpose="確認ボタン")
            if confirm_button:
                await confirm_button.click()
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(2000)

            submit_button = await smart_find(page, [
                'button:has-text("送信")',
                'button:has-text("応募する")',
                'input[type="submit"][value*="送信"]',
            ], purpose="送信・応募ボタン")
            if submit_button:
                await submit_button.click()
                await page.wait_for_load_state("domcontentloaded")
                await page.wait_for_timeout(2000)

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
                "success": False,
                "message": "送信処理完了したが完了メッセージを検出できず（要手動確認）",
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
