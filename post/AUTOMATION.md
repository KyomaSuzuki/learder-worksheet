# X自動投稿

- 投稿先はBufferに接続した唯一のXアカウント。複数ある場合、GitHub Actionsの変数 `BUFFER_CHANNEL_ID` で選択。
- 毎日09:00（日本時間）を日時指定して、7日先まで予約。初回実行の翌朝から開始（直前15分以内は翌々朝）。
- GitHub Actionsは毎日12:17（日本時間）に補充。実行が多少遅れても、投稿はBufferの予約時刻に実施。
- `x_posts.md` の24テーマ×A〜Eの120本を使用。同じテーマは24本間隔。共通投稿は対象外。
- 120本終了後は自動生成・再利用せず停止。停止期間の原稿は飛ばさず、次の空き日程へ予約。
- Secretsの `WORKSHEET_AUTO_POST` を使用（実行時は環境変数 `BUFFER_API_KEY` に渡す）。キーをソースに書かない。

## 確認・停止

GitHub → Actions → Daily X posts via Buffer。Run workflowのpublish=falseは接続確認・プレビューのみ。trueは予約を補充。
停止時はワークフローをDisableにするだけでなく、Buffer側のキューをPauseする（予約済みの投稿も停止するため）。
失敗はGitHub Actionsの失敗通知を使用。GitHubの通知設定でActionsのメール通知を有効にする。

## 重複防止

`buffer_state.json` に予約前のpending記録をpushしてからAPIを呼び、成功後にBufferのIDを記録する。
通信が途切れて結果不明の場合、次回はBufferの投稿一覧と照合。予約が見つからなければ自動再送せず停止。
この場合はBufferで実際の予約状況を確認し、未作成を確認できた場合だけ対応するpending記録を削除して再実行する。
進捗コミットは毎日のリポジトリ更新にもなる。公開リポジトリの60日間無活動による定期実行停止は、全原稿終了後など進捗更新がなくなった際に起こり得る。

## ローカル検証

```
python3 -m unittest discover -s tests -v
python3 scripts/buffer_queue.py --validate
```

API仕様: https://developers.buffer.com/guides/posts-and-scheduling.html
