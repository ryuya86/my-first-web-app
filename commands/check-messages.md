# タスク: CrowdWorksメッセージ巡回

## 目的
CrowdWorksにログインし、未読メッセージを確認。各メッセージに対してAI返信案を生成し、Slackで承認を待つ。

## 手順

### Step 1: ブラウザでCrowdWorksにログイン
Playwrightを使ってCrowdWorksにログインする。

```python
from playwright.async_api import async_playwright
import asyncio, os

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # ログイン
        await page.goto("https://crowdworks.jp/login", timeout=30000)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(2000)

        # ログインフォームを探して入力（セレクタは固定しない）
        # page.content() でHTMLを確認し、適切なフィールドを特定する
```

**重要**: CSSセレクタをハードコードしない。`page.content()` でHTMLを読み、入力フィールドとボタンを自分で特定する。

### Step 2: メッセージ一覧を確認
`https://crowdworks.jp/messages` に移動し、未読メッセージのあるスレッドを特定する。

### Step 3: 各スレッドの内容を取得
未読スレッドを開き、会話履歴を読み取る。
- 最新メッセージが自分（送信済み）の場合はスキップ
- `state/seen_messages.json` で既に処理済みならスキップ

### Step 4: 返信案を生成
クライアントのメッセージ内容に基づき、適切な返信案を生成する。
`templates/reply-templates.md` のガイドラインを参照。

返信案は `python tools/ng_checker.py` で必ずNGチェックする。

### Step 5: Slack通知
返信案をSlackに送信し、CEOの承認を待つ。
```
python tools/slack_notify.py message_received '{"client":"クライアント名","preview":"メッセージ概要","thread_url":"URL","reply_draft":"返信案","phase":"フェーズ"}'
```

**絶対に自動送信しない。** 返信案の生成とSlack報告のみ行う。

### Step 6: 状態更新
処理したメッセージを `state/seen_messages.json` に記録する。
DB記録: `python tools/db.py log-message '{json}'`

## 注意事項
- ブラウザ操作は2秒以上の間隔を空ける
- タイムアウトしたらスクリーンショットを撮り、Slackにエラー報告
- 最大5スレッドまで処理（コスト制限）
