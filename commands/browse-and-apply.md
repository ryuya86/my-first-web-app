# タスク: 承認済み案件への自動応募

## 目的
`state/apply_queue.json` に保存されたpending案件に、Playwrightでブラウザ操作して応募する。

## 手順

### Step 1: キューを確認
`state/apply_queue.json` を読み込み、`status` が `"pending"` の案件を取得する。
pendingがなければ「応募待ち案件なし」とSlackに報告して終了。

### Step 2: CrowdWorksにログイン
Playwrightでヘッドレスブラウザを起動し、CrowdWorksにログインする。

```python
from playwright.async_api import async_playwright
import asyncio, os

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto("https://crowdworks.jp/login", timeout=30000)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(2000)
        # HTMLを確認してログインフォームの要素を特定する
```

**重要**: CSSセレクタをハードコードしない。`page.content()` でHTMLを確認し、適切な要素を自分で特定する。

### Step 3: 案件ページを読んで提案文を生成
pending案件ごとに以下を実行:

1. 案件URLに移動し、案件の詳細（要件・報酬・納期）を読み取る
2. `templates/proposal-guidelines.md` のガイドラインに従い、案件内容に合わせた提案文を生成する
3. `python tools/ng_checker.py '提案文'` でNGチェックを通す。NGがあれば修正する
4. 生成した提案文を `state/apply_queue.json` の該当案件の `proposal` フィールドに保存する

### Step 4: 応募実行
提案文が準備できた案件に応募する:

1. 案件ページで「応募画面へ」「この仕事に応募する」等のボタンを探してクリック
2. 提案文入力欄を見つけ、生成した提案文を入力する
3. 確認画面 → 送信ボタンをクリック
4. 完了メッセージが表示されたことを確認する

**各操作の間は2秒以上の間隔を空ける。**

### Step 4: 結果の記録
- 応募成功: `state/apply_queue.json` の該当案件の status を `"applied"` に更新
- 応募失敗: status を `"failed"` に更新、エラー内容を記録

DBにも記録: `python tools/db.py log-job '{json}'`

### Step 5: Slack報告
応募結果をSlackに報告:
```
python tools/slack_notify.py report '{"title":"応募完了報告","body":"✅ 応募成功: X件\n❌ 失敗: Y件\n\n詳細:\n- 案件名1: 応募完了\n- 案件名2: エラー（理由）"}'
```

## 注意事項
- 1回の実行で最大3件まで応募する（アカウント保護）
- エラーが起きたらスクリーンショットを撮影し、別のアプローチを試みる
- 3回失敗したらその案件はスキップしてSlackに報告
- 応募完了後は必ずブラウザを閉じる
