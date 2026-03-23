# タスク: 週次レポート

## 目的
1週間の活動を振り返り、改善点を提案するレポートをSlackに送信する。

## 手順

### Step 1: 統計取得
`python tools/db.py stats` と `python tools/db.py stats-category` で統計を取得。

### Step 2: レポート作成
```
📊 週次レポート（MM/DD 〜 MM/DD）

■ 数値サマリー
- 案件スキャン: XXX件
- スコア通過: XX件
- 応募: XX件
- 返信あり: XX件
- 契約: XX件
- 売上: ¥XXX,XXX

■ カテゴリ別
- データ入力: X件応募 / Y件契約
- スクレイピング: X件応募 / Y件契約
- ...

■ 改善提案
（統計から読み取れるアクションアイテムを3つ以内で提案）
```

### Step 3: Slackに送信
```
python tools/slack_notify.py report '{"title":"📊 週次レポート","body":"内容..."}'
```
