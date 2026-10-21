# claude_workspace

Claudeが開発・調査・整理に使う場所。**リリースには含めない**（ルールは [RELEASE_RULES.md](RELEASE_RULES.md)）。

## 中身

| ファイル・フォルダー | 内容 |
|---|---|
| `AI_RULES.md` | **Claude・ChatGPT共通の作業ルール**（マッピング、テスト範囲、テスト削除前の確認、不要箇所の扱い）と削減候補一覧。ルート直下の`CLAUDE.md`・`AGENTS.md`から参照 |
| `CLAUDE.md` | コードマップ。Claudeが編集する時の地図 |
| `HANDOFF.md` | 引き継ぎメモ。作業の遵守事項と残作業 |
| `HANDOFF.en.md` | 引き継ぎメモの英語版 |
| `REVIEW_REQUEST.en.md` | コードレビュー依頼票（英語） |
| `RELEASE_RULES.md` | リリースに含めないためのルールと強制の仕組み |
| `verification/` | リファクタの旧新比較スクリプト |

以前はv1.1時点のソースの軽量コピーを置いていたが、本体と別物になり二重管理になるため2026-10-21に削除した。ソースの実体は常にリポジトリ直下を参照する。
