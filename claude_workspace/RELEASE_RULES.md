# リリース除外ルール

`claude_workspace/` は **Claude用の開発場所**であり、**リリース（配布フォルダー・配布ZIP・更新ZIP）に含めてはならない**。

## ルール

1. `claude_workspace/` の中身は、配布フォルダー（`dist/KarenDrop/`）にコピーしない。
2. 配布ZIP・更新ZIPの中に `claude_workspace` を含めない。ネストした場所（例：`assets/claude_workspace/`）も同様。
3. リリース対象は許可リスト方式で決まる。`claude_workspace` を許可リストへ追加しない。
   - `drop_tool/updater.py` の `TOP_FILES` / `TOP_DIRS`
   - `tools/build_exe.py` がコピーする名前（`assets`, `references`, `dictionary-docs`, `models`, `licenses` と指定ファイル）
4. 新しい最上位フォルダーを作る場合も、許可リストに入れない限り配布されない。この性質を壊さない。
5. リリースを作る前に、下の確認コマンドで混入がないことを確かめる。

## 強制の仕組み

| 仕組み | 場所 | 動作 |
|---|---|---|
| 許可リスト | `tools/build_exe.py`、`drop_tool/updater.py` | 名前を指定した物だけを配布へ入れる。更新時は許可外のファイルを含むZIPを拒否する（`safe_path`） |
| 混入ガード | `tools/package_release.py` の `RELEASE_EXCLUDED_DIRS` / `forbidden_paths` | 配布フォルダーに `claude_workspace` が1つでもあると、manifestもZIPも作らず停止する。ZIP作成後も中身を再確認し、混入があればZIPを破棄する |
| テスト | `tests/test_release_exclusion.py` | 上記の動作（通常・最上位混入・ネスト混入・最終確認）を検証する |

除外するフォルダーを増やす場合は、`tools/package_release.py` の `RELEASE_EXCLUDED_DIRS` に名前を足し、このファイルの表と下のテストを更新する。

## リリース前の確認コマンド

```
python tools/run_tests.py
python tools/build_exe.py dist
python tools/package_release.py dist/KarenDrop KarenDrop-vX.Y-windows.zip
```

`package_release.py` が「リリースに含めてはならないフォルダーが配布フォルダーにあります」と出して停止したら、混入を取り除いてからやり直す。ガードを外して回避しない。

## 守ること（Claude向け）

- `claude_workspace/` を許可リスト・ビルドスクリプト・更新ZIPの対象に加える変更は、理由に関わらず行わない。
- `RELEASE_EXCLUDED_DIRS` から `claude_workspace` を消す変更は行わない。変更が必要な場合は利用者に相談する。
- 公開前は `AGENTS.md` に従い、リモートの変更・ブランチ・タグ・Release添付を確認してから進める。既存タグ・公開済み配布物は置き換えない。
