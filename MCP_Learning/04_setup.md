# MCPのセットアップ

## 必要なもの
- Node.js (v18以上)
- Claude Desktop または Claude Code

## インストール手順
1. MCPサーバーパッケージをインストール
   ```
   npm install @modelcontextprotocol/server-filesystem
   ```

2. 設定ファイルを作成 (`claude_desktop_config.json`)
   ```json
   {
     "mcpServers": {
       "filesystem": {
         "command": "node",
         "args": ["path/to/server/index.js"]
       }
     }
   }
   ```

3. Claudeを再起動してMCPサーバーを有効化

## 動作確認
Claudeとの会話でMCPツールが使えることを確認しましょう。
