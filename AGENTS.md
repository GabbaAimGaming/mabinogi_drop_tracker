# GitHub公開前の確認

KarenDropをGitHubへ反映・公開する直前に、毎回リモートのソース、ブランチ、タグ、Release添付を前回確認時と比較する。他の管理者の変更を上書きせず、取り込み・競合解決・再検証を行う。判断が必要な変更は公開前に利用者へ相談する。既存タグや公開済み配布物は新しい版で置き換えない。

# AI作業ルール

このリポジトリで作業するAI（ChatGPT/Codex、Claude等）は、作業の前に[`claude_workspace/AI_RULES.md`](claude_workspace/AI_RULES.md)を読み、そこに書かれた4つのルール（マッピングの作成と更新、テストの範囲、テストコードを消す前の確認、不要箇所の扱い）を守る。コードマップは[`claude_workspace/CLAUDE.md`](claude_workspace/CLAUDE.md)。`claude_workspace/`はリリースに含めない。
