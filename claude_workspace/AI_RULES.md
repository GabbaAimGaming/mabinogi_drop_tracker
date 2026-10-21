# AI作業ルール（Claude・ChatGPT共通）

このリポジトリで作業するAI（Claude、ChatGPT/Codex等）は、作業の前にこのファイルを読み、以下の4つを必ず守る。2026-10-22 利用者指示。
入口はリポジトリ直下の`CLAUDE.md`（Claude Code用）と`AGENTS.md`（ChatGPT/Codex用）。どちらもこのファイルを指すだけで、ルールの本体はここに1つだけ置く。
このファイルは`claude_workspace/`にあるため、リリース（配布フォルダー・ZIP・更新ZIP）には入らない（[RELEASE_RULES.md](RELEASE_RULES.md)）。

ほかの約束（作業ブランチは`claude/dev-workspace`、公開前の確認は`AGENTS.md`、リリース除外は`RELEASE_RULES.md`）も引き続き有効。食い違う場合はこのファイルを優先し、利用者に報告する。

## ルール1：マッピング（コードマップ）を作り、保つ
- コードの地図は[CLAUDE.md](CLAUDE.md)（このフォルダー内のコードマップ）。作業の前に読む。
- ファイルの追加・移動・削除、モジュールの責務や依存の変更、データ形式・設定項目の追加をしたら、**同じコミットで**コードマップを更新する。最低限、§3「モジュール表」と§5「変更したい内容 → 触る場所」。依存の向きが変わったら§1、保存データが変わったら§4も。
- 地図と実コードが食い違っているのを見つけたら、実コードを正として地図を直す。

## ルール2：テストの範囲
- **普段**：変更に関係する機能のテストだけを回す。
  - 新しく足した処理には基本のテストを書いて回す。
  - 退行確認は、変更に関係する過去機能のテストだけ。
- **全量テスト**（`python tools/run_tests.py`）は**リリース直前に1回だけ**回す（[RELEASE_RULES.md](RELEASE_RULES.md)の確認コマンドの1つ目）。利用者が明示的に指示した時も回す。
- テストは`tools/run_tests.py`経由で回す（`tests/_headless.py`の代役が入るため）。個別に回す時も同じスクリプトへテスト名を渡す。
  - 例：`python tools/run_tests.py test_learning test_item_links`（モジュール名・`tests/test_x.py`のパス・`モジュール.クラス.メソッド`が使える。引数なしは全量。読み込めない名前があれば実行せずに失敗する）
- 回した範囲（件数・skip数・対象）は報告とコミットメッセージ、または引き継ぎメモに残す。

## ルール3：テストコード・テストファイルを消す前に、本体での利用を確かめる
- テスト用のコード・ファイル（`tests/`配下、テスト専用の関数・データ・画像等）を消す前に、本体が参照していないかを検索する。本体とは、`drop_tool/`、ルートの`app.py`・`bootstrap.py`等、`tools/build_exe.py`が配布へ入れる物（`assets`、`references`、`models`、`dictionary-docs`、`licenses`、指定ファイル）。
- **本体が使っているなら、それはテストコードではない。** 消さずに本体側の正式な置き場所（例：`drop_tool/`の該当モジュール、`assets/`）へ移し、配布物に含まれるようにする。
  - 配布物は許可リスト方式（`updater.TOP_FILES/TOP_DIRS`、`tools/build_exe.py`）で決まる。既存の許可リストの範囲内へ置く。許可リスト自体を広げる必要がある時は、利用者に相談する。`claude_workspace`・`tests`は許可リストに入れない。
  - 移した時は、ルール1に従ってコードマップを更新する。
- 本体が使っていないことを確かめた物でも、すぐには消さない。ルール4の手順に乗せる。
- 逆の向き（本体の関数をテストだけが使っている。例：`vision.label_presence`）は、本体側の不要箇所としてルール4で扱う。

## ルール4：不要な箇所は「コメントアウト → 候補一覧 → 利用者が判断 → 削除」
1. **1回目（見つけた時）**：消さずにコメントアウトする。1行で理由を添える。
   - 形式：`# [削減候補 YYYY-MM-DD] 何が・なぜ不要か。確認後に削除`
   - 依存するテストも同じ印でコメントアウトかskipにする。
   - 下の「削減候補一覧」に追記する。
2. **次回リリースの準備に入ったら**：削除する前に、`[削減候補`で検索して候補を一覧にし、利用者に提示する（場所・内容・理由・依存テスト）。
3. **利用者が「問題ない」と判断した物から削除する。** 判断が出ていない物、保留と言われた物は消さない（コメントアウトのまま次回へ持ち越す）。
4. 削除したら、本体・テストの両方から消し、一覧の状態を「削除済み（コミット）」へ更新し、関係するテストを回す（ルール2）。
- 例外：利用者が個別に「消していい」と明示した物は、そのまま削除してよい。
- 挙動が変わる削除（呼び出し元がある、保存データに関わる等）は不要箇所として扱わない。先に利用者へ相談する。

### 削減候補一覧
2026-10-21の段階6で付けた印（`[削減候補 2026-10-21]`）も、このルールに乗せる（2026-10-22 利用者指示。以前の「利用者の指示があるまで待機」は、この手順に置き換えた）。v1.1.9のリリース準備で一覧を提示し、判断を仰ぐ。詳細は[HANDOFF.md](HANDOFF.md)§3。

| 印の日付 | 場所 | 内容・理由 | 依存テスト | 状態 |
|---|---|---|---|---|
| 2026-10-21 | `drop_tool/manual_actions.py` | `App.test_image`：呼び出し元なし | — | 未判断 |
| 2026-10-21 | `drop_tool/manual_actions.py` | `App.timed_read`：本体から呼ばれない | `test_capture_flow`の停止中1件 | 未判断 |
| 2026-10-21 | `drop_tool/manual_actions.py`・`sample_actions.py` | `App.countdown`へ集約したカウントダウンの旧実装 | — | 未判断 |
| 2026-10-21 | `drop_tool/retention.py` | `EVIDENCE_KEYS`・`load_settings`・`save_settings`：本体は`settings.load/save`を使う | `test_evidence_retention`の旧行コメント | 未判断 |
| 2026-10-21 | `drop_tool/chest_gradients.py` | `GradientClassifier.compute`：`cv2.HOGDescriptor`互換の名残 | — | 未判断 |
| 2026-10-21 | `drop_tool/vision.py` | `vision.similarity`：照合は`mask_similarity` | — | 未判断 |
| 2026-10-21 | `drop_tool/vision.py` | `Vision.learn`と`import copy`：v0.18.2以降呼ばれない。固有動作はv1.1.8の`learning.add`が引き継いだ | `test_tracker`・`test_item_catalog`・`test_resource_limits`の旧行コメントと停止中1件。`test_item_catalog.test_image_learning_and_row_change_rollback_together`は`test_learning`側との整理が必要 | 未判断 |
| 2026-10-21 | `drop_tool/app.py` | 分割で移動先へ移ったimportと`STATUS/KIND` | — | 未判断 |

印の付いていない検討中の物（一覧には入れない。印を付けるかを利用者と相談）：`vision.label_presence`（非公開テストだけが使う）、`'captured'`イベント（実機の`errors.log`で様子見。HANDOFF.md§6）。
