# タスク: 新着案件の収集とスコアリング

## 目的
CrowdWorksのRSSフィードから新着案件を収集し、マッチングスコアを算出し、高スコア案件をSlackに通知する。

## 手順

### Step 1: RSS案件取得
`python tools/rss_collector.py` を実行する。
結果はJSON配列で標準出力に出力される。新着案件がなければ空配列`[]`が返る。

新着なしの場合はSlackに「新着案件なし」と報告して終了する。

### Step 2: マッチングスコアリング
各案件について、以下の基準で0〜100点のスコアを算出する。
`templates/crowdworks-profile.md` のスキルセットを参照し、自分の判断でスコアをつける。

**評価基準（合計100点）:**
1. **自動化適性 (35点)**: AI・RPA・スクレイピング・データ処理など自動化で効率化できるか
2. **報酬妥当性 (20点)**: 作業量に対して報酬が妥当か（実績作りフェーズなので低報酬でもOK）
3. **要件の明確さ (15点)**: 要件・成果物が明確か
4. **リスクの低さ (30点)**: トラブルリスクが低いか（過剰な期待・短すぎる納期は大幅減点）

### Step 3: 提案文生成
スコア40点以上の案件について、提案文を生成する。
`templates/proposal-guidelines.md` のガイドラインに従うこと。

提案文を生成したら、`python tools/ng_checker.py '提案文テキスト'` でNGチェックを通す。
NGが検出されたら修正してから次に進む。

### Step 4: DB記録
各案件を `python tools/db.py log-job '{json}'` で記録する。
JSONには `id`, `title`, `url`, `category`, `score`, `proposal` を含める。

### Step 5: Slack通知
各案件を `python tools/slack_notify.py job_found '{json}'` で通知する。
JSONには `title`, `url`, `score`, `category`, `summary`, `proposal` を含める。

### Step 6: 完了報告
全案件の処理が終わったら、処理結果のサマリーをSlackに報告する:
```
python tools/slack_notify.py report '{"title":"案件収集完了","body":"新着: X件 / スコア通過: Y件 / スキップ: Z件"}'
```

## 注意事項
- 案件が多い場合は、スコアが高い順に最大10件まで処理する
- エラーが発生しても他の案件の処理は続行する
- 全体でエラーがあった場合は最後にまとめてSlackに報告する
