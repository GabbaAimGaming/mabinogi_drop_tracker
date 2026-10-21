# Claude向けの入口

作業の前に次の2つを読むこと。どちらも`claude_workspace/`にあり、リリースには含めない。

1. [`claude_workspace/AI_RULES.md`](claude_workspace/AI_RULES.md)：Claude・ChatGPT共通の作業ルール（マッピングの作成と更新、テストの範囲、テストコードを消す前の確認、不要箇所の扱い）。必ず守る。
2. [`claude_workspace/CLAUDE.md`](claude_workspace/CLAUDE.md)：コードマップ。引き継ぎは[`claude_workspace/HANDOFF.md`](claude_workspace/HANDOFF.md)。

公開（push・PR・Release）の前は[`AGENTS.md`](AGENTS.md)の確認を行う。このファイルにはルールを書き足さず、`AI_RULES.md`を更新する。
