# 引き継ぎメモ：リファクタリング（2026-10-22 更新／v1.1.8）

作業場所は **`claude/dev-workspace`**。地図は[CLAUDE.md](CLAUDE.md)、リリース除外は[RELEASE_RULES.md](RELEASE_RULES.md)。英語版は[HANDOFF.en.md](HANDOFF.en.md)、レビュー依頼票は[REVIEW_REQUEST.en.md](REVIEW_REQUEST.en.md)。

**現在の状態：v1.1.8としてmainへ統合済み。削減2回目（削除）は利用者の指示待ち。**
- 2026-10-22：作者側（VerGumiSlime）がdev-workspaceへ3コミットを追加し、PR #10でmainへマージ、タグ`v1.1.8`とReleaseを公開した（§9）。
- dev-workspaceはmainのコピーとして`1618462`（＝`v1.1.8`）へ揃えた。以後、この上の差分は`claude_workspace/`の文書だけ。
- PR本文では`a21135c`を「レビュー済み整理版」としている。依頼票の質問への個別の回答は受け取っていない。

## 0. 遵守事項（2026-10-21 利用者指示。必ず守る）
1. **作業は`claude/dev-workspace`の上で行う。** `refactor/*`等の別ブランチを切らず、dev-workspaceへ直接コミットする。
   - **dev-workspaceは`main`のコピーを持つ**（2026-10-22 利用者指示）。mainが進んだら取り込んでから作業を始める。
2. **不要コードはいきなり消さない。2段階で進める。**
   - 1回目：コメントアウトする（何がなぜ不要かを1行コメントで添える。例：`# [削減候補 2026-10-21] 呼び出し元なし。確認後に削除`）。依存するテストも同様にコメントアウトかskipにする。
   - 2回目：利用者が確認して問題なしと言ったら削除する。
   - 例外：利用者が個別に「消していい」と明示したもの（例：`claude_workspace/`のv1.1ソースコピー）はそのまま削除してよい。

## 1. 元の依頼と全体の流れ
- **依頼**：KarenDrop（マビノギのドロップ記録ツール、v1.1.7）のコードを、**挙動を変えずに**整理する。最終目標は「無駄を削ったコードの軽量化」と「肥大したコードの役割分割」。
- **進め方**：
  1. **整理（段階0〜5）**：テストを回せる土台を作り、大きい処理を分け、重複をまとめた。行数はむしろ増えた（整形とdocstringのため）。
  2. **削減1回目（段階6）**：使われていないコードを洗い出し、コメントアウトした（削除はまだ）。
  3. **分割（段階7）**：936行の`app.py`を役割ごとに4ファイルへ分けた。
  4. **レビューと統合**：担当者にdev-workspace全体を見てもらった。作者側がPR #10でmainへ統合し、v1.1.8として公開（§9）。
  5. **削減2回目（今ここ・待機）**：利用者の指示後、`[削減候補 2026-10-21]`の箇所を実際に削除する。
- **全段階で共通の約束**：挙動は変えない。変わっていないことを、段階ごとに旧版と新版へ同じ入力を流して比べる方法で確認した（§2の右列）。

## 2. 段階ごとの要約

| 段階 | コミット | 内容 | 挙動不変の確認 |
|---|---|---|---|
| 0 | `673d2ed` | `tests/_headless.py`：tkinter・winsound・`WinDLL`が無い環境だけ代役を入れ、ロジック系テストをLinuxで実行可能に。`updater._is_link`へリンク判定を集約 | 159件実行・22エラー → 246件成功 |
| 1 | `e7a42e8` | `App.submit`の`work()`を`drop_tool/read_worker.py`へ（`run`/`_observe`/`_burst`）。`poll`→`handle_job`＋mode対応表。`getattr`既定値をクラス属性へ。`app.py`の詰め書きを整形 | 旧新に同じ入力を流す14シナリオでキュー出力一致（`verification/compare_worker.py`） |
| 1' | `cc40969` | `'captured'`イベントの受信処理をコメントアウト（様子見）。届いたら`errors.log`に記録して無視 | テスト1件をskip |
| 2 | `15eab7e` | `red_labels`＋`purple_labels`→`color_labels.py`（`red`/`purple`）。`vision.boxes`の重なり判定を`_overlaps`へ集約 | 合成画像316枚で候補・`Vision.boxes`・`quick_check`・倍率補正が全件一致（`compare_vision.py`） |
| 3 | `0f21f81` | `ChestDetector.detect`を段の並び（`_near_plates`/`_detail`/`_parts`）に。補助検出器は`cached_property` | 各段を差し替えた384通りで採用結果・呼び出し順・生成回数が一致（`compare_chest.py`）。画像比較は意味が薄いため不実施（CLAUDE.md §7） |
| 4 | `5b41d7a` | `names.py`（`normalize`）、`reading.py`（`StableReading`/`consensus`）を`tracker`から分離。`tracker`は再エクスポート。`item_links`の手書き正規化2か所を`normalize`へ | 移した8定義は構文木が同一。`Store`・`records.json`は不変 |
| 5 | `dff05b1` | `updater`を分割せず、中を「取得/検証/適用・復旧/配布者用」に並べ替え、重複値を定数化 | 定数を元の値へ戻した構文木で33定義が一致 |
| 統合 | `45f9be6` | dev-workspaceへマージ。`package_release.py`は混入ガード＋mainの同梱物削減を両立 | 251件成功（`test_release_exclusion`含む） |
| 整備 | `415d48f` | 遵守事項（§0）を追記。`claude_workspace/`のv1.1ソースコピーを削除（利用者OK） | 251件成功 |
| 6 | `1a7b565` | **削減1回目**：未使用コードをコメントアウト。3秒カウントダウンを`App.countdown`へ集約（§3） | 関連テスト89件成功。新しい`report_missed`のテストが旧コードでも通ることを確認 |
| 7 | `a24cb34` | **分割**：`app.py`から`HistoryActions`・`ManualActions`・`SampleActions`へメソッドを移動。`ui.build_widgets`を領域ごとの関数へ（§4） | 63メソッドが構文木で同一、参照先も同一（`compare_split.py`）。画面部品の呼び出し171件が一致（`compare_ui.py`）。`compare_worker.py`一致。関連テスト96件成功 |
| 文書 | `a21135c` | 引き継ぎメモ更新、英語版・レビュー依頼票、段階7の検証スクリプト | — |
| v1.1.8 | `e4ac676`〜`1618462` | 作者側：容量制限付きローカル学習（`learning.py`）、PR #10でmainへ統合・公開（§9） | 作者側で263件（35件skip）成功。こちらで関連101件成功 |

## 3. 削減1回目（段階6）の中身
印は`[削減候補 2026-10-21]`で検索できる。

| 対象 | 理由 | テストの扱い |
|---|---|---|
| `App.test_image` | 呼び出し元なし。`review_capture`を呼ぶだけ | — |
| `App.timed_read` | 本体から呼ばれない（docstringに「旧呼び出し用」） | `test_capture_flow`の1件を停止 |
| `retention.EVIDENCE_KEYS`・`load_settings`・`save_settings` | 本体は`settings.load/save`を直接使う。`load_settings`も未使用と途中で判明 | `test_evidence_retention`を`settings.load/save`経由へ書き換え |
| `GradientClassifier.compute` | `cv2.HOGDescriptor`互換の名残。`ChestShape`は`detectMultiScale`だけ使う | — |
| `vision.similarity` | 照合は`mask_similarity`で作成済みマスク同士を比べる | — |
| `Vision.learn`（と`vision`の`import copy`） | 下の「経緯」参照 | 公開2本と非公開`test_tracker`の2件を`assign`経由へ書き換え。`learn`固有の1件を停止 |
| カウントダウン3か所 | `capture_manual`・`report_missed`・`timed_read`に同じ処理。`App.countdown(秒数, 文言, mode)`へ集約し、旧実装はコメントで残す | `report_missed`の基本テストを追加 |

**`Vision.learn`の経緯**：誤読を手で直した時に品名画像を見本として覚える関数。最初のコミット（10/13）から、`correct_row`が呼んで行の名前を直接書き換えていた。v0.18.2（10/18）で`item_registration.assign`に置き換わった（元の読み取り名を残し、`item_links`で誤読名→正式名を対応付ける方式）。それ以降、本体からは呼ばれていない。`learn`だけが持っていた「ほぼ同じ見本（類似度0.98以上）を記録から外す」動きは`assign`に無い。ただし読込時の`Vision.reload`でも同じ基準で間引くので、照合への影響は無い。違いは`records.json`の`templates`が少しずつ伸びうる点だけ。

**対象外にしたもの**：`vision.label_presence`（非公開`test_window_share`だけが使う1行のラッパー。扱いは利用者と相談）。`'captured'`イベント（実機での様子見中、§6）。

## 4. 分割（段階7）の中身
- `app.py`（936行→471行）：起動・設定・前面撮影・監視ループ・読取結果の振り分け（`handle_job`、`apply_live`、`read_failed`）。
- `history_actions.py`（`HistoryActions`）：履歴と統計の表示、行の選択とプレビュー、辞書登録`correct_row`、確定・対象外・削除、CSV出力、未登録名の通知。表示名`STATUS`・`KIND`もここへ。
- `manual_actions.py`（`ManualActions`）：`countdown`、3秒後の撮影、撮影画像の確認・読取、手動読取の保存、周回内の修正。
- `sample_actions.py`（`SampleActions`）：提出用サンプルの保存、「読めなかった」報告、ZIP出力。
- `App`がこの3つを継承する（`class App(HistoryActions, ManualActions, SampleActions)`）。3つは`__init__`もクラス属性も持たず、Appの属性を前提にする混ぜ込み用クラス。
- `ui.build_widgets`（143行）は、同じファイルの中で`_controls`・`_notes`・`_stats_tab`・`_review_tab`へ。部品を作る順番は変えていない。触ったので詰め書き1行だけ整形した。
- `app.py`で使われなくなったimportと`STATUS/KIND`は、§0に従ってコメントアウト（移動先に実体がある）。

## 5. 判断の記録（なぜそうしたか）
- **キューの型はタプルのまま**：テストが`(epoch, mode, result, error)`の素のタプルを入れて`poll`を検証しているため。
- **本体のimportを関数内へ移さない**：テストがモジュール属性をpatchしている。
- **`updater`は分割しない（案A）**：テストが`updater.build_opener`・`download`・`check`等を約20か所patchしている。分割すると、移した先の関数が自分のモジュールの名前を参照するためpatchが効かず、テスト中に実通信が起きうる。通信まわりの追加機能の予定もない。
- **`App`は混ぜ込みクラス（Mixin）で分割する**：`ui.py`の`command=self.xxx`と、テストの`App.__new__(App)`をそのまま使えるため。
- **`App`分割ではテストのpatch先を変えなかった**：当初は書き換えが必要と見ていた（利用者OK済み）。しかし`patch('drop_tool.app.messagebox.askyesno')`は`tkinter.messagebox`モジュール自体の属性を差し替えるので、移動先のモジュールでも効く。`updater`と違い、patch対象が「自分のモジュールの名前」ではないため。
- **宝箱は画像で比較しない**：合成画像には箱が写らないため、全段が未検出になる。実際に116枚中116枚が未検出で、「どれも無い」の1経路しか通らなかった。
- **整形は触ったファイルだけ**：全体を一括整形すると差分が膨らむため。整形済みは`app.py`、`read_worker.py`、`vision.py`、`color_labels.py`、`chest_detector.py`、`updater.py`。新規の`*_actions.py`は元の書き方のまま移した（構文木の比較を優先）。
- **`Vision.learn`の依存テストは消さず書き換えた**：テストが守っていた性質（見本が再起動後も照合できる、利用者の除外指定が同梱素材より優先、保存失敗で全体が戻る）は今の経路でも守るべきため。

## 6. 残っていること（優先順）
1. **削減2回目は待機**：利用者の指示があるまで`[削減候補 2026-10-21]`を消さない（2026-10-22 利用者指示）。指示が出たら下の4へ。
2. **Windowsでの確認**：作者側でv1.1.8のソース全体263件（35件skip）・配布EXE内11件・自己診断が成功と報告あり（PR #10）。実機での各タブ・ボタン・自動/手動読取の確認結果は未受領。
3. **非公開画像テスト（利用者の環境で）**：
   - 段階2：`test_red_labels`、`test_purple_labels`、`test_cyan_labels`、`test_label_*`
   - 段階3：`test_reward_samples`、`test_4k_review`、`test_next_4k_samples`、`test_new_person_samples`、`test_closed_oct19`、`test_chest_*`
   - 段階1・4・6：`test_alt_display`、`test_window_share`、`test_tracker`（段階6で学習2件を`assign`経由へ書き換えた。こちらではskipを外して単体で成功を確認済み）
4. **削減2回目**：利用者の指示後、`[削減候補 2026-10-21]`の箇所（本体・テスト）を削除する。v1.1.8の配布物にはコメントアウトのまま入っている（動作への影響なし）。
   - `Vision.learn`：唯一の固有動作（ほぼ同じ見本を外す）はv1.1.8の`learning.add`が引き継いだので、削除の支障はない。
   - `test_item_catalog.test_image_learning_and_row_change_rollback_together`：段階6で`assign`経由へ書き換えたが、扱いが`review`のためv1.1.8では画像を学習せず、画像の巻き戻しまでは確かめていない。同じ性質は`test_learning.test_failed_save_restores_old_sample_and_removes_new_file`が確かめている。削除時にどちらへ寄せるか整理する。
5. **`'captured'`の様子見**：実機で`errors.log`に「想定外のcapturedイベントを受信しました」が一度も出なければ、まとめて削除する。対象は`App.handle_job`の見張り、`App.show_progress`のコメント、`test_alt_display`のskip中テスト1件、`notification.SOUNDS['captured']`。
6. **`vision.label_presence`の扱い**：利用者と相談。
7. **改行コードの統一**（相談中）：v1.1.8で8ファイルがまるごとCRLFになった（§9）。`.gitattributes`を足すかLFへ戻すかを利用者と決める。決まるまで変換しない。編集時はそのファイルの改行コードを保つ。
8. **リモートの`refactor/step*`ブランチ6本の削除**（利用者がGitHubのBranches画面から。セッションの権限ではHTTP 403で拒否された）。
9. **mainへ戻す時**：PRを作る時は`AGENTS.md`の公開前確認に従う（混入ガード`RELEASE_EXCLUDED_DIRS`はv1.1.8でmainにも入った）。

## 7. 利用者との約束（作業の進め方）
- §0の遵守事項（dev-workspaceで作業、不要コードはコメントアウト→確認→削除）。
- コーディング前に実装方針を一度共有する。
- ソースの提示は差分。全量は指示があった時だけ。
- 正確性・拡張性・改修のしやすさを最重視する。挙動を変える変更は事前に相談する。
- テスト：新規分は基本テスト、退行は関連する過去機能だけ。全量テストは指示があった時。
  - 段階0〜5は`tools/run_tests.py`（約10秒）を毎回回した。段階6・7は関連テストだけ回した（89件・96件）。全量はまだ回していない。
- 公開（push・PR・Release）の前に`AGENTS.md`の確認を行う。

## 8. 検証スクリプト（`verification/`）
旧版は`git worktree add <場所> <旧コミット>`で用意して、旧新それぞれでスクリプトを実行し、結果を比べる。
- `compare_worker.py`：`App.submit`/`read_worker`のキュー出力（14シナリオ）。引数：リポジトリ。出力JSONを旧新で比べる
- `compare_vision.py`：色付き品名・`Vision.boxes`・`quick_check`・倍率補正（合成画像316枚）。引数：リポジトリ、出力JSON
- `compare_chest.py`：宝箱検知の段の制御（384通り）。画像比較部分はコメントアウト。引数：リポジトリ、出力JSON
- `compare_split.py`：段階7。引数：旧リポジトリ（`1a7b565`）、新リポジトリ。メソッドの構文木と参照先の同一性を表示
- `compare_ui.py`：段階7。引数：旧リポジトリ（`1a7b565`）、新リポジトリ。`build_widgets`の部品呼び出し列とAppの属性を比較

テストを回す時は`tests/_headless.py`の代役を使うため、`python tools/run_tests.py`経由で実行する（`python -m unittest`単体だと代役が入らない）。

## 9. v1.1.8（2026-10-22、作者側の統合）
作者側（VerGumiSlime）が`a21135c`の上に3コミットを足し、PR #10でmainへマージ、タグ`v1.1.8`とReleaseを公開した（添付：`KarenDrop-v1.1.8-windows.zip`、`recovery-guide.txt`、`update-info.json`）。

| コミット | 内容 |
|---|---|
| `e4ac676` | v1.1.8の文書（README、README_EXE、更新内容、更新方法） |
| `e007bb3` | 容量制限付きのローカル学習`drop_tool/learning.py`を追加。`assign`が`learning.add`を使う。`Vision.reload`は見本が無い・壊れていても読み飛ばす。`App.prune_evidence`が起動時に`learning.maintain`を呼ぶ。版数1.1.8 |
| `daa425b` | `tests/test_learning.py`（11件）を追加。`test_item_links`の1件を「参照先の無い旧見本は外す」挙動へ修正 |
| `1618462` | PR #10のマージ（mainのみ） |

- **中身の変更は+351/−35行**。GitHubの差分表示が約4,200行に見えるのは、8ファイル（`drop_tool/app.py`・`vision.py`・`updater.py`・`item_registration.py`・`preflight.py`、`tests/test_item_links.py`、`README.md`、`README_EXE.txt`）の改行コードがまるごとCRLFになったため。`.gitattributes`は無い。
- **学習の仕様**：1品3枚・全体1000枚・合計16MB・1枚128KB。似た見本（0.98以上）と古い見本を自動で整理する。学習するのは`material`/`excluded`だけで、結合画像・複数行・アイコン状の画像は覚えない。新しい見本は`labels/auto-<24hex>.png`。
- **データへの影響（仕様どおり、READMEに記載）**：起動時の整理で1品3枚を超える既存見本と、参照されない自動生成画像（旧版のハッシュ名を含む）を消す。`references/`や証拠画像には触れない。
- **段階6との関係**：段階6で「`learn`だけが持つ」とした「ほぼ同じ見本を外す」動きは、`learning.add`がより厳しい形で持つようになった（依頼票の質問5は実質解決）。
- **こちらでの確認**（Linux）：取り込み後に関連テスト101件が成功（`test_learning`、`test_item_links`、`test_item_catalog`、`test_resource_limits`、`test_evidence_retention`、`test_manual_review`、`test_capture_flow`、`test_v11_settings`、`test_karen_ui`、非公開`test_tracker`の学習2件）。
