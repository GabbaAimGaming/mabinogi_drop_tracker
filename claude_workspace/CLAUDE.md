# KarenDrop コードマップ（v1.1.7 ＋ リファクタ作業中）

Claudeが編集する際の地図。実コードとテスト実行結果に基づく。**作業ブランチ：`claude/dev-workspace`**（`main` `5ed115c`＝タグ`v1.1.7`に、リファクタ段階0〜5を統合済み。段階は§9、経緯は[HANDOFF.md](HANDOFF.md)）。
パスはすべてリポジトリ直下からの相対。このフォルダー（`claude_workspace/`）はリリースに含めない（[RELEASE_RULES.md](RELEASE_RULES.md)）。

## 0. 前提と絶対ルール
- **作業は`claude/dev-workspace`へ直接コミットする（別ブランチを切らない）。不要コードはまずコメントアウトし、利用者の確認後に削除する。**詳細は[HANDOFF.md](HANDOFF.md)§0。
- Windows専用。Python 3.12、tkinter、OpenCV、ONNX Runtime（OCR）。依存は`requirements.txt`の4つ（Pillow、numpy、opencv-python、onnxruntime）。
- ユーザーデータは`data/`（gitignore対象）に置く。**既存データを壊さない**ことが最優先。
- `records.json`は`version=1`固定。形式が違えば上書きせず停止する。互換を崩す変更は禁止。
- 変更パターンは統一してある。`deepcopy`で退避 → 変更 → `save()` → 失敗したら復元。新しい書き込み処理もこの形に揃える。
- 集計の分母は`status=='confirmed'`の周回だけ。`review`の行は集計しない。v1.1.6から、**現在の除外設定を過去の確認済み周回にも集計時だけ適用**する（元の行は書き換えない）。
- ルート直下の`tracker.py`と`vision.py`は旧import用の互換入口（3行、`import *`）。ロジックは足さない。`drop_tool.tracker`は`normalize`・`StableReading`・`consensus`を互換のため再エクスポートしている（テストが`from tracker import ...`で使う）。新しいコードは本来の置き場所（`names`、`reading`、`config.ROOT`）からimportする。
- 新機能の置き場所は`*_views.py`や専用モジュール。`App`には委譲だけ書く（各docstringの方針）。
- 公開前は`AGENTS.md`に従い、リモートのソース・ブランチ・タグ・Release添付を前回確認時と比較する。既存タグや公開済み配布物は置き換えない。
- `claude_workspace/`や`tests/`をリリースへ入れない。配布物は`updater.TOP_FILES/TOP_DIRS`の**許可リスト方式**で絞っている（`tools/package_release.py`はこの一覧と`release-manifest.json`・`exclusions.json`・`update-source.json`だけをZIPへ入れる）ので、許可リストへ追加しない。
  - `claude/dev-workspace`ではさらに`tools/package_release.py`の`RELEASE_EXCLUDED_DIRS`/`forbidden_paths`が、配布フォルダー・ZIPに`claude_workspace`が混ざると停止する（`tests/test_release_exclusion.py`）。これを消さない。詳細は[RELEASE_RULES.md](RELEASE_RULES.md)。この仕組みは`main`にはまだ無い（dev-workspaceだけ）。
- テストはモジュール属性をpatchする（例：`drop_tool.app.messagebox.showerror`、`drop_tool.app.capture.active`、`drop_tool.update_view.messagebox.askyesno`、`drop_tool.notification.winsound.PlaySound`）。**本体のimportを関数内へ移すとテストが壊れる**ので、モジュール先頭のimportは維持する。
- テストは`App.__new__(App)`で属性を一部だけ入れた`App`を作り、`app.jobs`へ**素のタプル**`(epoch, mode, result, error)`を入れて`poll`を検証する。キューの型は変えない。`__init__`を通らなくても参照される値は`App`の**クラス属性**に既定値を置く（`settings`、`settings_views`、`samples`、`reward_gate`、`chest_detector`、`near_detector`、`scan_trace`、`manual_target`、`saved_read_target`、`saved_read_expected`）。どれも読むだけか代入で差し替える値に限る。

## 1. レイヤーと依存の向き

```
app.py(起動) → drop_tool/app.py(App ＝ HistoryActions＋ManualActions＋SampleActions) → ui.py → *_views.py
                      │  └ read_worker（撮影・認識ワーカー。Tk非依存）
        ┌─────────────┼───────────────────────┐
     撮影/判定        認識                     記録/集計
 windows_capture    vision ── ocr_engine      tracker(Store/Rules)
 chest_detector     label_*/alt_display       item_catalog / item_links
  ├ chest_fragments  hud_filter/hud_text      item_registration
  ├ chest_shape      plate_recovery           manual_review
  ├ chest_parts      bright_plates            exporting / csv_collection
  └ chest_gradients  color_labels(赤・紫)     retention / settings
 near_dialog        label_detection
 reward_gate        alt_capture ── reading(StableReading/consensus)
                     （全員の土台：config.ROOT、names.normalize。どちらも依存なし）
```

段階4で`tracker`を分割した。`normalize`は`names.py`（依存なし）、複数フレームの多数決は`reading.py`。`tracker`に直接依存するのは`Store`・`Rules`・`default_near`・`SHADOW_MISSIONS`を使うモジュール（`app`、`exporting`、`item_catalog`、`vision`）だけになった。`Store`の変更は今も影響範囲が最大。
`Store.stats`は関数内で`ItemCatalog`をimportする（`item_catalog`が`tracker`をimportするため、循環を避けている）。
注意：自前の`drop_tool/windows_capture.py`（前景ウィンドウの撮影）と、廃止したpipパッケージ`windows-capture`は別物。

## 2. データフロー（自動読取）
1. `App.tick`が350ms（中央スキャン）または700msで回り、`submit('live')`を呼ぶ。前面のゲーム画面だけを撮影する（`App.ready`が前面でなければ読まない）。
2. `App.submit`は開始時点のepoch・対象ゲーム・対象周回・中央スキャン設定を固定し、`read_worker.run`を別スレッドで起動する。ワーカーは`app.grab`で撮影し、`_observe`で`near_dialog`（確認画面の除外）、`App.reward_detection`（`chest_detector`）、`alt_display.quick_check`を見る。
3. `RewardGate`が宝箱 + ALT表示の3秒継続を判定する。未成立なら`scan`イベントで待機メッセージを返す。
4. 成立したら`start`イベントを返し、`_burst`が`alt_capture.collect`で連写、`alt_capture.read`で`Vision.analyze`に通す。
5. `Vision.analyze`は画像から品名を作る。
   - `boxes`で切り抜く。白・緑の通常経路 → `label_detection.recover_rows`（発光） → `color_labels.red` → `color_labels.purple`（白・緑の品名があれば、その近くの行だけ） → 断片の結合・ゲージ除外・`alt_display.select` → 2枚未満なら`plate_recovery`と`bright_plates`で補う → `split_labels`。
   - 見本照合`recognize_template`（類似度0.92以上、次点との差0.035以上）。
   - 駄目ならOCR（`ocr_engine.suggestions`）。`hud_text`で百分率・時刻を除く。
   - `ItemCatalog`で正式名と種別に解決する。
6. 結果は`jobs`キュー（`(epoch, mode, result, error)`のタプル）に入り、`App.poll`（150ms）が`handle_job`へ渡す。`start/captured`は途中経過（busyを解除しない）、`epoch`が違えば古い結果として破棄、`error`があれば`read_failed`。それ以外はmode→処理の対応表（`show_scan`、`save_missed`、`sample_saved`、`sample_error`、`save_manual_photo`、`apply_saved_read`、`show_test`、`save_manual_reading`、既定は`apply_live`）。
7. 複数フレームは`reading.StableReading`（3回一致、または`consensus`の多数決）で1周分に確定する。
8. `Store.persist_rows`で証拠画像を保存し、`Store.record`で保存する。自動読取も`require_review=True`で`status=review`。
9. 利用者が確認して`Store.confirm`すると`confirmed`になり、`Store.stats`と`exporting`に載る。

`ChestDetector.detect`のフォールバック順：全体SIFT（`search='full'`） → `_near_plates`（`plate_rows`を1回求め、`ChestFragments` → `ChestShape`。いずれも近くのALT品名板が条件） → `_detail`（幅1600px超だけ、蓋の候補と中央を原寸で再探索、`search='detail'`） → `_parts`（`ChestParts`、`parts`キーを除く）。最初に見つかった段の結果を採用し、どれも無ければ全体SIFTの結果。`seconds`は全段の合計で上書き。補助の検出器は`cached_property`で初回利用時に作る。

手動系の`submit`モード：`manual`（1枚読取、必ず`review`）、`manual_photo`（撮影だけして周回に紐付け、`manual_review.save_photo`）、`saved_read`（周回に紐付いた画像を解析し`manual_review.replace_reading`）、`missed`（読めなかった報告用サンプル）、`test`。影ミッションの自動開始は実ゲーム未検証なので、手動読取が確実な経路。

## 3. モジュール表

| 領域 | ファイル | 責務・主要シンボル | 主なテスト |
|---|---|---|---|
| 起動 | `app.py` | `run_app/main`、`--self-test`、`--diagnose`、二重起動ガード | test_portability |
| 起動 | `bootstrap.py` / `start.bat` / `診断.bat` | 配布用の起動準備、環境診断の起動 | — |
| 設定 | `config.py` | `ROOT`（EXE版は実行ファイルの隣）、`configure_tk`（凍結版のTcl/Tk） | test_tk_runtime |
| 画面 | `drop_tool/app.py` | `App`（約470行）：起動・設定・前面撮影・監視ループ・読取結果の振り分け。`submit/poll/handle_job/tick/apply_live/read_failed`。下の3クラスを継承する | test_karen_ui, test_capture_flow, test_v11_settings, test_reward_scan_reuse |
| 画面 | `drop_tool/history_actions.py` | `HistoryActions`：履歴・統計の表示、行の選択とプレビュー、辞書登録`correct_row`、確定・対象外・削除、CSV出力、未登録名の通知。表示名`STATUS`・`KIND` | test_item_links, test_evidence_retention, test_karen_ui |
| 画面 | `drop_tool/manual_actions.py` | `ManualActions`：`countdown`、3秒後の撮影`capture_manual`、撮影画像の確認・読取`review_capture/apply_saved_read`、手動読取の保存、周回内の修正`edit_this_run` | test_manual_review |
| 画面 | `drop_tool/sample_actions.py` | `SampleActions`：提出用サンプルの保存（別スレッド）、`report_missed`、ZIP出力 | test_manual_review, test_capture_flow |
| 画面 | `drop_tool/read_worker.py` | 撮影・認識ワーカー（Tk非依存）。`run`、`_observe`（取得条件の判定）、`_burst`（連写と多数決）、`middle`（中央範囲） | test_near_dialog, test_manual_review, test_capture_flow（連写成立は非公開のtest_alt_display/test_window_share） |
| 画面 | `ui.py` | `build_widgets`（`_controls`・`_notes`・`_stats_tab`・`_review_tab`へ分割）。ダンジョン選択（影ミッション5種）・難易度（`エリート`）、タブ「ドロップ統計」「周回履歴・確認待ち」＋CSV2タブ | test_karen_ui |
| 画面 | `item_views.py` / `settings_views.py` / `csv_views.py` / `update_view.py` | 「アイテム管理」「設定」、CSV比較の2タブ、更新・旧版への復旧UI | test_item_links, test_csv_*, test_startup_update, test_old_release_dropdown, test_rollback |
| 画面部品 | `theme.py` `scrollable.py` `karen_banner.py` `image_display.py` | 配色・スクロール・表示補助 | — |
| 撮影 | `windows_capture.py` | 前景ゲームウィンドウの読み取り専用撮影（読み込み時に`ctypes.WinDLL('user32')`） | test_capture_flow |
| 判定 | `chest_detector.py` | 宝箱検出（`assets/chests/*.npz`のSIFT）と段の並び`detect`（`_near_plates/_detail/_parts`） | test_reward_samples, test_4k_review, test_next_4k_samples |
| 判定 | `chest_fragments.py` `chest_shape.py` `chest_parts.py` `chest_gradients.py` | 箱の補助判定（表面マスク、蓋の形、蓋と本体の部品照合、勾配セル分類器） | test_chest_fragments, test_chest_shape, test_chest_parts, test_closed_oct19 |
| 判定 | `reward_gate.py` `near_dialog.py` | 3秒ゲート、ネアル確認画面の除外 | test_near_dialog, test_reward_scan_reuse |
| 判定 | `alt_display.py` `alt_capture.py` | ALT品名板の判定と連写 | test_alt_display, test_alt_hold_simulation |
| 認識 | `vision.py` | `Vision`：切り抜き`boxes`・見本照合・OCR（`learn`は段階6でコメントアウト。学習は`item_registration.assign`）。枠の重なり判定は`_overlaps(boxes, y, x, width, tolerance)` | test_tracker ほか |
| 認識 | `label_images.py` `label_scale.py` `label_detection.py` `plate_recovery.py` `hud_filter.py` | マスク生成（`text_pixels/red_pixels/purple_pixels`等）、倍率補正、発光時の補助検出、HUD除外 | test_label_*, test_glow_recovery, test_hud_filter, test_cyan_labels |
| 認識 | `color_labels.py` | 赤・紫文字の補助候補。`red/purple`が共通の`_candidates`へ色ごとの条件（密度範囲・色画素の比・紫の字形条件）を渡す。`vision.boxes`、`alt_display`、`label_scale`（`max_height=44`）が使う | test_red_labels, test_purple_labels |
| 認識 | `bright_plates.py` `hud_text.py` | 色光の上の半透明板の復元、百分率・時刻の除外 | test_bright_plates, test_hud_text |
| 認識 | `ocr_engine.py` | `models/japanese-rec.onnx`で推論。通信・GPUなし | test_local_ocr, test_color_ocr |
| 記録 | `tracker.py` | `Store`（`records.json`）、`Rules`、`SHADOW_MISSIONS`、`default_near`。`normalize/StableReading/consensus`は互換の再エクスポート | test_tracker（非公開fixtures）、test_statistics_exclusions |
| 記録 | `names.py` | `normalize`（NFKC＋空白除去）。品名比較の共通土台 | test_item_links ほか |
| 認識 | `reading.py` | `StableReading`（3回一致・8フレームで多数決・離した時の採用）、`consensus`（位置ごとの多数決、同名板の小移動許容） | test_moving_labels, test_alt_display |
| 記録 | `manual_review.py` | 手動撮影の保存（`evidence/<run_id>/manual-*.png`）、周回の読み直し・行編集、確定後の撮影画像整理 | test_manual_review |
| 辞書 | `item_catalog.py` | `item-master.json`の読込、`classify/candidates/search/set_policy` | test_item_catalog, test_dictionary_supplement |
| 辞書 | `item_links.py` `item_registration.py` | 名前の対応付け（誤読名→正式名）と登録。`name_key`は`normalize`＋数量括弧除去＋スクロール表記の統一 | test_item_links |
| 出力 | `exporting.py` `csv_collection.py` | CSV出力と、他の人のCSVの読込・集計 | test_exporting, test_csv_* |
| 保守 | `retention.py` `settings.py` | バックアップ・ログ・証拠画像の世代管理、`settings.json` | test_evidence_retention, test_resource_limits, test_v11_settings |
| 保守 | `notification.py` `sample_reports.py` `preflight.py` `instance_guard.py` | 完了音、提出用サンプル、環境診断、mutex | 各`test_*` |
| 更新 | `updater.py` `update_helper.ps1` | 更新確認・検証・適用・旧版への復旧。中は「定数 → 取得（`download`、`check`、`old_releases`等） → 検証（`validate_info`、`version_key`、`safe_path`、`digest`、`_is_link`） → 適用・復旧（`new_work`、`cleanup`、`prepare`、`stage`、`launch`、`rollback_removals`） → 配布者用（`make_info`）」の区切り。共通の値は`USER_AGENT`、`DRIVE_HOSTS`、`SHA256_PATTERN`、`ZIP_ROOT`、`ZIP_MANIFEST`。`VERSION='1.1.7'`、許可リスト`TOP_FILES/TOP_DIRS` | test_updater, test_github_update, test_rollback, test_startup_update, test_old_release_dropdown, test_ssl_runtime |
| 開発 | `tools/*` `build_exe.py` | EXEビルド、ZIP作成（`package_release.py`、許可リスト方式＋`claude_workspace`混入ガード）、宝箱テンプレ生成、旧版フィード作成`make_legacy_feed.py`、SSL同梱`ssl_runtime.py`、ベンチ | test_release_exclusion, test_release_contents |

## 4. 保存データ

**`data/records.json`**
```
version: 1
runs[]: {id, dungeon, difficulty, near('使用'|'不使用'), created, status, rows[],
         capture_image?}   # 手動撮影 evidence/<id>/manual-<hex>.png（manual_review.owned_captureで検証）
  status: waiting / review / confirmed / discarded
  row: {name, raw, kind(material|excluded|review), image(相対パス),
        reviewed_kind?, resolved_name?}
templates[]: {name, kind, path}      # 学習した見本画像 (data/labels/)
overrides{}: 正規化名 -> kind        # 手動指定が最優先
item_links{}: 誤読名 -> 正式名       # 集計時に解決。元の行は書き換えない
item_names[]: 登録名
player_name?: 追加キー（旧版互換）
```
`default_near(dungeon, difficulty)`：影ミッション5種は`不使用`、アルビHDは`使用`、それ以外は`未指定`（`new_run`は`未指定`を受け付けないので画面で選ばせる）。
`Rules`は読み込み時に`フィニージェム/フィニージエム`を除外接頭辞へ補う（旧版の個別JSON対策。`overrides`が最優先なのは従来通り）。

**`data/settings.json`**（`settings.py`の`DEFAULTS`と`_valid`が正）
`evidence_auto_delete`、`evidence_keep_runs`、`scan_mode`（full/center）、`auto_reward`、`update_url`。旧`window_share`は読んでも無視し、保存時に除去する。

**周辺ファイル**
- `data/backups/`、`data/evidence/`、`data/labels/`、`data/提出用サンプル/`、`last-loot-capture.png`、`errors.log`、更新用の`.updates/`。
- 配布側の読み取り専用データ：`item-master.json`（schema_version 1、440品、`dictionary_version` `2026-10-18.1`）、`exclusions.json`、`references/labels.json`、`assets/chests/manifest.json`、`models/manifest.json`、`release-manifest.json`（復旧時の削除対象の確認）。

## 5. 変更したい内容 → 触る場所

| やりたいこと | 触る場所 |
|---|---|
| 素材/除外の判定ルール | `exclusions.json`、`Rules.classify`、`ItemCatalog.classify` |
| 辞書に品を追加 | `item-master.json`、`item_catalog.py`、`dictionary-docs/` |
| 誤読名の対応付け | `item_links.py`、`item_registration.py` |
| OCR・照合の精度 | `vision.py`（閾値）、`ocr_engine.py`、`label_images.py` |
| 色付き品名の検出 | `color_labels.py`（色を足すなら関数を1つ追加）、`label_images.py`の`*_pixels`、`vision.boxes` |
| ALT品名板の検出 | `alt_display.py`、`label_detection.py`、`plate_recovery.py`、`bright_plates.py` |
| 複数フレームの多数決 | `reading.consensus` / `StableReading`、`tests/test_moving_labels.py` |
| 取得タイミング・宝箱 | `read_worker._observe/_burst`、`reward_gate.py`、`alt_capture.py`、`chest_*.py`（検出方式を足すなら`ChestDetector`に段のメソッドを作り`detect`の並びへ1つ追加）、`assets/chests/` |
| 読取結果の画面反映 | `App.handle_job`の対応表と各処理（`apply_live`等） |
| 手動撮影・周回内の修正 | `manual_review.py`、`manual_actions.py`（`capture_manual/review_capture/edit_this_run`） |
| 履歴・統計の画面操作 | `history_actions.py` |
| 提出用サンプル | `sample_actions.py`、`sample_reports.py` |
| 集計・出現率 | `Store.stats/confirm`、`exporting.py` |
| ダンジョン・難易度の追加 | `ui.py`のコンボ値、`tracker.SHADOW_MISSIONS`/`default_near`、`tests/test_v11_settings.py` |
| 設定項目の追加 | `settings.py`（DEFAULTS+`_valid`）、`settings_views.py`、`App.save_setting` |
| タブ・画面の追加 | 新規`*_views.py`を作り、`ui.py`から組み込む |
| バージョン更新 | `updater.VERSION`、`App`のタイトル、`DEVELOPMENT.md`、README類、`更新内容.txt`、`update-source.json` |
| リリースの組み立て | `tools/build_exe.py`、`tools/package_release.py`、`tools/ssl_runtime.py`、`RELEASE_RULES.md` |

## 6. v1.1 → v1.1.7 の変更点（コミットとコードで確認したもの）
- **v1.1.1〜1.1.3**：4Kと夢幻ラビの宝箱検知を改善（`chest_fragments/shape/parts/gradients`、細部探索）。赤・紫・水色の品名と発光した品名板の認識（当時の`red_labels`・`purple_labels`→段階2で`color_labels`へ統合、`bright_plates`、`label_images`の色マスク）。起動時の更新案内。
- **v1.1.4**：手動撮影を周回に結び付ける（`manual_review`）、周回内の修正、画像整理、旧版への復旧（`updater.old_releases/rollback_removals`、`update_view`のドロップダウン）。
- **v1.1.5**：復旧候補をドロップダウンを開いた時に読む。紫の品名文字の保持。
- **v1.1.6**：現在の除外設定を過去の統計へ反映（`Store.stats`）。配布物の整理。
- **v1.1.7**：配布EXEのHTTPS通信に必要なファイル不足を修正（`tools/ssl_runtime.py`、`test_ssl_runtime`）。
- `App`は829行 → 946行（v1.1.7時点）。

## 7. テストの実態
`python tools/run_tests.py`で実行する。

**ヘッドレス実行（リファクタ段階0で追加）**：`tools/run_tests.py`は起動時に`tests/_headless.py`の`install()`を呼ぶ。tkinter・winsound・`ctypes.WinDLL`が**無い環境だけ**代役を入れ、Windowsでは何もしない。
- 実画面を作る処理（`tk.Tk()`等）や、patchされていないWindows API呼び出しは`SkipTest`になる（成功扱いにしない）。
- テストがpatchする属性（`messagebox.*`、`winsound.PlaySound`）は存在するので、patch済みのロジックは検証できる。
- `test_instance_guard`は非Windowsでモジュールごとskip。
- `python -m unittest`で個別に回す場合は代役が入らない。`tools/run_tests.py`経由で回す。

Linux（Python 3.13、tkinterなし）での結果：**251件実行、成功、skip 55件**（`claude/dev-workspace`。`test_release_exclusion`の5件を含む）。
- skipの内訳：非公開の提供・提出画像が必要（chest_fragments 11、closed_oct19 3、next_4k_samples 3、new_person_samples 2、chest_parts/chest_shape/red_labels 各1、「別途検証済み」のモジュール13＝alt_display、window_share、tracker等）、実画面が必要（karen_ui 10、item_links 5、evidence_retention 4）、Windows専用（instance_guard）。
- 段階0以前はimportできなかった`manual_review`、`rollback`、`updater`、`github_update`、`startup_update`、`old_release_dropdown`、`v11_settings`、`reward_scan_reuse`、`capture_flow`、`notification`、`resource_limits`がLinuxでも回る。

**公開テストで通らない経路**：自動読取の連写成立（`read_worker._burst`）は`test_alt_display`と`test_window_share`（非公開の動画フレーム）でしか通らない。段階1では旧`App.submit`と新`read_worker`へ同じ入力を流し、14シナリオ（成立・中央/全体・2枚未満・解析例外・待機3種・epoch変更・各手動モード）でキュー出力・scan_trace・worker_phaseが一致することを確認した。
**色付き品名**：`test_red_labels`の実画像テストは非公開。段階2では旧新に同じ316枚（テストの赤・紫合成画像、参照品名、乱数で色文字・板・ゲージ・発光を置いた画像）を流し、`red/purple`（max_height 18/44）、`Vision.boxes`（全体・中央）、`quick_check`、`recognition_scale`が全件一致することを確認した。

**宝箱検知**：段階3では画像を流す比較は行わず、各段を「見つかる/見つからない」に差し替えた384通り（全体SIFT・表面マスク・蓋の形・画面幅1280/1920・蓋の候補0/2件・細部探索で当たる領域・`evidence_box`の有無・部品照合、各2回呼び出し）で、採用結果・段の呼び出し順・検出器の生成回数が旧版と一致することを確認した。
- **画像比較の意味が薄い理由**：宝箱の検出は利用者提供の箱の見本（`assets/chests/*.npz`のSIFT特徴）との照合と、箱の表面・蓋の形・部品の見本で成り立っている。合成画像（品名板、色文字、ゲージ、発光）には箱が写っていないので、どの段も見つからない。実際に段階2の合成画像116枚を実物の検出器へ流すと、116枚すべてが「全体SIFTで未検出」のまま最後まで進んだ。つまり通るのは「どれも無い」の1経路だけで、段の順序・採用する結果・座標の戻し方・`parts`キーの除去の違いは検出できない。
- そのため比較スクリプト`verification/compare_chest.py`の画像比較部分はコメントアウトで残している。実画像（非公開の`work/4k-*`等）がある環境では、`test_reward_samples`、`test_4k_review`、`test_next_4k_samples`、`test_new_person_samples`、`test_closed_oct19`、`test_chest_*`を回すのが本当の確認になる。

**比較スクリプト**（このプロジェクトの`verification/`。リポジトリには含めない）：引数は比較したいリポジトリの作業コピーと出力JSON。旧版は`git worktree add <場所> <旧ブランチ>`で用意し、旧新の出力JSONを比べる。
- `compare_worker.py`：段階1。旧`App.submit`と`read_worker`のキュー出力（14シナリオ）。
- `compare_vision.py`：段階2。合成画像316枚で色付き品名・`Vision.boxes`・`quick_check`・倍率補正。
- `compare_chest.py`：段階3。宝箱検知の段の制御（384通り）。
- `compare_split.py`・`compare_ui.py`：段階7。`App`分割のメソッド同一性と、`build_widgets`の部品呼び出し列（引数は旧・新リポジトリ）。

`test_tracker`（`Store`・`StableReading`の中核テスト）は公開環境ではskipされる。保存と確定のロジックを直す時は、公開テストだけだと守りが薄い。認識・宝箱系の退行は非公開画像のある作者側環境で確認してもらう。

## 8. 注意ゾーン
- **`drop_tool/app.py`**：約470行（2026-10-21に履歴・手動・サンプルを分割）。変更は小さく、新規ロジックは別モジュールへ。
- **`*_actions.py`はAppへ混ぜ込むクラス**：`__init__`を持たず、Appの属性（`store`、画面部品等）を前提にする。テストの`patch('drop_tool.app.messagebox.…')`は`tkinter.messagebox`モジュール自体の属性を差し替えるので、メソッドを別モジュールへ移しても効く（`from tkinter import messagebox`で同じモジュールを参照する限り）。
- **認識の閾値**（0.92、0.035、`CENTER`、`MAX_FRAMES`、`consensus`の移動許容幅、各`*_labels`の高さ・幅・密度条件等）：非公開画像でしか回帰を確認できない。変更は事前に相談。
- **Windows依存**：`winsound`、`ctypes.WinDLL`、`st_file_attributes`（`updater._is_link`で非Windowsは0扱い）。実機の動作はLinuxでは確認できない。
- **宝箱検知は試験機能**：未収集の角度や小さい箱は見逃す。`chest_parts`はdocstring上「ローカル試作用」。
- **書き方の混在**：新しめのモジュール（`chest_*`、`manual_review`等）は`;`で1行に詰めた書き方が多い。方針：段階ごとに**触ったファイルだけ**整形する（`app.py`は段階1、`vision.py`・`color_labels.py`は段階2で整形済み。`alt_display.py`・`label_scale.py`は触った行だけ）。

## 9. リファクタリング計画（2026-10、挙動は変えない／最終目標は無駄を削った軽量化）
0. **済**：ヘッドレス実行、このコードマップの更新（ブランチ`refactor/step0-safety-net`）
1. **済**：`App`の分解（ブランチ`refactor/step1-app`）。`submit`内の`work()`を`read_worker`へ移設、`poll`を`handle_job`＋対応表に、`getattr`既定値をクラス属性へ、`app.py`の`;`詰めを整形。キューのdataclass化はテストが素のタプルに依存するため見送り。
2. **済**：`vision.boxes`の重なり判定を`_overlaps`へ集約、赤・紫のループを1本に。`red_labels`と`purple_labels`を`color_labels`へ統合して2ファイル削除（ブランチ`refactor/step2-vision`）
3. **済**：`ChestDetector.detect`を段の並び（`_near_plates/_detail/_parts`）に、補助検出器を`cached_property`に（ブランチ`refactor/step3-chest`）。docstringと整形で行数は+30
4. **済**：`tracker`の分割（ブランチ`refactor/step4-tracker`）。`names.normalize`、`reading.StableReading/consensus`へ移設し`tracker`から再エクスポート。使う側は直接import（`ROOT`は`config`から）。`item_links`の手書き正規化2か所を`normalize`へ。移した8定義は構文木で旧版と同一、`records.json`・`Store`は不変
5. **済（案A）**：`updater`はファイルを分けず、中を「取得／検証／適用・復旧／配布者用」の区切りに並べ直し、重複した値を定数へ集約、詰め書きを整形（ブランチ`refactor/step5-updater`）。
   - 分割しなかった理由：テストが`updater.build_opener`・`download`・`check`・`prepare`・`cleanup`・`new_work`・`launch`・`old_releases`・`sys`をモジュール属性としてpatchしている（約20か所）。別ファイルへ移すと、移した先の関数が自分のモジュールの名前を参照するためpatchが効かず、テスト中に実通信が起きうる。通信まわりに追加機能の予定もなく、分割の恩恵が薄いと利用者と判断した。
   - 確認：新しい定数を元の値へ戻した構文木で、33定義とimportが旧版と全件一致。

6. **済（削減1回目）**：未使用コードを`[削減候補 2026-10-21]`でコメントアウト、カウントダウンを`App.countdown`へ集約（`1a7b565`）。削除はレビューと利用者確認の後。詳細は[HANDOFF.md](HANDOFF.md)§3
7. **済**：`app.py`を`HistoryActions`・`ManualActions`・`SampleActions`へ分割、`ui.build_widgets`を領域ごとの関数へ（`a24cb34`）。詳細は[HANDOFF.md](HANDOFF.md)§4
8. **レビュー待ち**（[REVIEW_REQUEST.en.md](REVIEW_REQUEST.en.md)）→ 削減2回目（削除）

**様子見中（影響が無ければ削除）**：
- `'captured'`イベント：本体のどこからも送られない。`App.show_progress`の表示処理はコメントアウト済み。`App.handle_job`の見張りが、届いた場合だけ`errors.log`へ「想定外のcapturedイベントを受信しました」と残して無視する。`test_alt_display.test_capture_event_plays_short_sound_without_ending_work`はskip。実機で一度も記録されなければ、見張り・コメント・テスト・`notification.SOUNDS['captured']`をまとめて削除する。
