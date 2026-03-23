# タスク: システムヘルスチェック

## 目的
各コンポーネントの動作状況を確認し、問題があればSlackに報告する。

## 手順

### Step 1: RSS接続テスト
`python tools/rss_collector.py` を実行し、RSSフィードから案件を取得できるか確認する。

### Step 2: DB状態確認
`python tools/db.py stats` を実行し、DBに正常にアクセスできるか確認する。

### Step 3: Slack接続テスト
`python tools/slack_notify.py report '{"title":"🏥 ヘルスチェック","body":"テスト通信"}'` で送信できるか確認する。

### Step 4: state/ ファイル確認
- `state/seen_jobs.json` が存在し、読み取り可能か
- `state/seen_messages.json` が存在し、読み取り可能か
- `state/history.db` が存在し、クエリ可能か

### Step 5: 結果報告
全コンポーネントの状態をSlackに報告する:
```
🏥 システムヘルスチェック
🟢 RSS接続: OK
🟢 DB: OK（レコード数: X件）
🟢 Slack: OK
🟢 state/: OK
```

問題があるコンポーネントは 🔴 で表示する。
