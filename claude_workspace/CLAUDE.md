# KarenDrop コードマップ（v1.1）

Claudeが編集する際の地図。実コードとテスト実行結果に基づく。作成時点：`main` `a79794c`（タグ`v1.1`）。
パスはすべてリポジトリ直下からの相対。このフォルダー（`claude_workspace/`）はリリースに含めない（[RELEASE_RULES.md](RELEASE_RULES.md)）。

## 0. 前提と絶対ルール
- Windows専用。Python 3.12、tkinter、OpenCV、ONNX Runtime（OCR）。依存は`requirements.txt`の4つ（Pillow、numpy、opencv-python、onnxruntime）。
- ユーザーデータは`data/`（gitignore対象）に置く。**既存データを壊さない**ことが最優先。
- `records.json`は`version=1`固定。形式が違えば上書きせず停止する。互換を崩す変更は禁止。
- 変更パターンは統一してある。`deepcopy`で退避 → 変更 → `save()` → 失敗したら復元。新しい書き込み処理もこの形に揃える。
- 集計の分母は`status=='confirmed'`の周回だけ。`review`の行は集計しない。
- ルート直下の`tracker.py`と`vision.py`は旧import用の互換入口（3行）。ロジックは足さない。
- 新機能の置き場所は`*_views.py`や専用モジュール。`App`には委譲だけ書く（各docstringの方針）。
- 公開前は`AGENTS.md`に従い、リモートのソース・ブランチ・タグ・Release添付を前回確認時と比較する。既存タグや公開済み配布物は置き換えない。
- `claude_workspace/`をリリースへ入れない。許可リストへ追加しない。`tools/package_release.py`の`RELEASE_EXCLUDED_DIRS`を消さない。

## 1. レイヤーと依存の向き

```
app.py(起動) → drop_tool/app.py(App) → ui.py → *_views.py
                      │
        ┌─────────────┼──────────────────┐
     撮影/判定       認識               記録/集計
 windows_capture   vision ── ocr_engine   tracker(Store/Rules/StableReading)
 chest_detector    label_*/alt_display    item_catalog / item_links
 near_dialog       hud_filter/plate_*     item_registration
 reward_gate       label_detection        exporting / csv_collection
                   alt_capture            retention / settings
```

`tracker.py`は`config.ROOT`、`Store`、`Rules`、`normalize`、`SHADOW_MISSIONS`の供給元で、ほぼ全員が依存する。ここの変更は影響範囲が最大。
注意：自前の`drop_tool/windows_capture.py`（前景ウィンドウの撮影）と、廃止したpipパッケージ`windows-capture`は別物。

## 2. データフロー（自動読取）
1. `App.tick`が350ms（中央スキャン）または700msで回り、`submit('live')`を呼ぶ。前面のゲーム画面だけを撮影する（`App.ready`が前面でなければ読まない）。
2. ワーカースレッドで撮影し、`near_dialog`で確認画面を除外する。次に`chest_detector`で宝箱、`alt_display.quick_check`でALT品名板を見る。
3. `RewardGate`が宝箱 + ALT表示の3秒継続を判定する。
4. 成立したら`alt_capture.collect`で連写し、`alt_capture.read`で`Vision.analyze`に通す。
5. `Vision.analyze`は画像から品名を作る。
   - `boxes`で切り抜く。
   - 見本照合`recognize_template`（類似度0.92以上、次点との差0.035以上）。
   - 駄目ならOCR（`ocr_engine.suggestions`）。
   - `ItemCatalog`で正式名と種別に解決する。
6. 結果は`jobs`キューに入り、`App.poll`（150ms）が受け取る。`epoch`が違えば古い結果として破棄する。
7. 複数フレームは`StableReading`（3回一致、または`consensus`の多数決）で1周分に確定する。
8. `Store.persist_rows`で証拠画像を保存し、`Store.record`で保存する。`require_review`の場合は`status=review`。
9. 利用者が確認して`Store.confirm`すると`confirmed`になり、`Store.stats`と`exporting`に載る。

手動読取は`submit('manual')`（5秒後の1枚）。このときは必ず`review`になる。影ミッションの自動開始は実ゲーム未検証なので、手動読取が確実な経路。

## 3. モジュール表

| 領域 | ファイル | 責務・主要シンボル | 主なテスト |
|---|---|---|---|
| 起動 | `app.py` | `run_app/main`、`--self-test`、`--diagnose`、二重起動ガード | test_portability |
| 起動 | `bootstrap.py` / `start.bat` / `診断.bat` | 配布用の起動準備、環境診断の起動 | — |
| 設定 | `config.py` | `ROOT`（EXE版は実行ファイルの隣） | — |
| 画面 | `drop_tool/app.py` | `App`：監視・履歴操作・サンプル提出。`submit/poll/tick/correct_row` | test_karen_ui, test_capture_flow, test_v11_settings |
| 画面 | `ui.py` | `build_widgets`。ダンジョン選択（影ミッション5種を含む）・難易度（`エリート`を含む）、タブ「ドロップ統計」「周回履歴・確認待ち」＋CSV2タブ | test_karen_ui |
| 画面 | `item_views.py` / `settings_views.py` / `csv_views.py` | 「アイテム管理」「設定」と、CSV比較の2タブ | test_item_links, test_csv_* |
| 画面部品 | `theme.py` `scrollable.py` `karen_banner.py` `image_display.py` | 配色・スクロール・表示補助 | — |
| 撮影 | `windows_capture.py` | 前景ゲームウィンドウの読み取り専用撮影 | test_capture_flow |
| 判定 | `chest_detector.py` `reward_gate.py` `near_dialog.py` | 宝箱検出（`assets/chests/*.npz`）、3秒ゲート、ネアル確認画面の除外 | test_reward_samples, test_near_dialog |
| 判定 | `alt_display.py` `alt_capture.py` | ALT品名板の判定と連写 | test_alt_display |
| 認識 | `vision.py` | `Vision`：切り抜き・見本照合・OCR・`learn`（学習） | test_tracker ほか |
| 認識 | `label_images.py` `label_scale.py` `label_detection.py` `plate_recovery.py` `hud_filter.py` | マスク生成、倍率補正、発光時の補助検出、HUD除外 | test_label_*, test_glow_recovery, test_hud_filter |
| 認識 | `ocr_engine.py` | `models/japanese-rec.onnx`で推論。通信・GPUなし | test_local_ocr, test_color_ocr |
| 記録 | `tracker.py` | `Store`（`records.json`）、`Rules`、`StableReading`、`consensus`、`SHADOW_MISSIONS`、`default_near` | test_tracker（非公開fixtures）、test_moving_labels |
| 辞書 | `item_catalog.py` | `item-master.json`の読込、`classify/candidates/search/set_policy` | test_item_catalog, test_dictionary_supplement |
| 辞書 | `item_links.py` `item_registration.py` | 名前の対応付け（誤読名→正式名）と登録 | test_item_links |
| 出力 | `exporting.py` `csv_collection.py` | CSV出力と、他の人のCSVの読込・集計 | test_exporting, test_csv_* |
| 保守 | `retention.py` `settings.py` | バックアップ・ログ・証拠画像の世代管理、`settings.json` | test_evidence_retention, test_resource_limits, test_v11_settings |
| 保守 | `notification.py` `sample_reports.py` `preflight.py` `instance_guard.py` | 完了音、提出用サンプル、環境診断、mutex | 各`test_*` |
| 更新 | `updater.py` `update_view.py` `update_helper.ps1` | 更新確認・検証・適用・復旧。`VERSION='1.1'`、許可リスト`TOP_FILES/TOP_DIRS` | test_updater, test_github_update |
| 開発 | `tools/*` `build_exe.py` | EXEビルド、ZIP作成（混入ガード付き）、宝箱テンプレ生成、ベンチ | test_release_exclusion |

## 4. 保存データ

**`data/records.json`**
```
version: 1
runs[]: {id, dungeon, difficulty, near('使用'|'不使用'), created, status, rows[]}
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

**`data/settings.json`**（`settings.py`の`DEFAULTS`と`_valid`が正）
`evidence_auto_delete`、`evidence_keep_runs`、`scan_mode`（full/center）、`auto_reward`、`update_url`。旧`window_share`は読んでも無視し、保存時に除去する。

**周辺ファイル**
- `data/backups/`、`data/evidence/`、`data/labels/`、`errors.log`。
- 配布側の読み取り専用データ：`item-master.json`（schema_version 1、v1.1は440品、`dictionary_version` `2026-10-18.1`）、`exclusions.json`、`references/labels.json`、`assets/chests/manifest.json`、`models/manifest.json`。

## 5. 変更したい内容 → 触る場所

| やりたいこと | 触る場所 |
|---|---|
| 素材/除外の判定ルール | `exclusions.json`、`Rules.classify`、`ItemCatalog.classify` |
| 辞書に品を追加 | `item-master.json`、`item_catalog.py`、`dictionary-docs/` |
| 誤読名の対応付け | `item_links.py`、`item_registration.py` |
| OCR・照合の精度 | `vision.py`（閾値）、`ocr_engine.py`、`label_images.py` |
| ALT品名板の検出 | `alt_display.py`、`label_detection.py`、`plate_recovery.py` |
| 複数フレームの多数決 | `tracker.consensus` / `StableReading`、`tests/test_moving_labels.py` |
| 取得タイミング・宝箱 | `reward_gate.py`、`alt_capture.py`、`chest_detector.py`、`assets/chests/` |
| 集計・出現率 | `Store.stats/confirm`、`exporting.py` |
| ダンジョン・難易度の追加 | `ui.py`のコンボ値、`tracker.SHADOW_MISSIONS`/`default_near`、`tests/test_v11_settings.py` |
| 設定項目の追加 | `settings.py`（DEFAULTS+`_valid`）、`settings_views.py`、`App.save_setting` |
| タブ・画面の追加 | 新規`*_views.py`を作り、`ui.py`から組み込む |
| バージョン更新 | `updater.VERSION`、`App`のタイトル、`DEVELOPMENT.md`、README類、`更新内容.txt`、`update-source.json` |
| リリースの組み立て | `tools/build_exe.py`、`tools/package_release.py`、`RELEASE_RULES.md` |

## 6. v1.0 → v1.1 の変更点（コードで確認したもの）
- **画面共有を廃止**：`drop_tool/window_share.py`削除、`windows-capture`を依存から削除。`App`の`toggle_share/stop_share/update_share/sharing`、設定画面の共有UI、`preflight.check_window_share`も削除。前面のゲーム画面を撮影する方式に統一。
- **影ミッション5種を追加**：`tracker.SHADOW_MISSIONS`、`default_near`、`ui.py`のコンボ（難易度に`エリート`）。
- **`consensus`の改良**：同名の品名板は小さな移動を許す（縦12px以内、横の重なり65%以上、幅比70%以上）。フレーム内は一対一で割り当て、同じ品が複数落ちても票を混ぜない。
- **辞書**：414品 → 440品。ペルシウス系オーブの追加と、オーブ先頭「ベルシウス」の限定補正（補正の実装箇所は未確認）。
- **宝箱テンプレ**：青く発光した開封済み宝箱の見本（`blue-open-v11-*.npz`と`-small`版）を追加。
- **テスト**：`test_moving_labels.py`、`test_v11_settings.py`を追加。`test_window_share.py`は中央スキャンのテストだけが残り、名前が実態と合わない（非公開fixturesでskip）。
- **運用**：`AGENTS.md`（公開前確認）、`docs/検証-v1.1.md`を追加。

## 7. テストの実態
`python tools/run_tests.py`で実行する。Linux環境（Python 3.13、tkinterなし）で個別に回した結果は次の通り。

- **全部通る**（46件）：color_ocr、csv_collection、csv_filters、dictionary_supplement、exporting、item_catalog、moving_labels、portability、release_exclusion。
- **一部通る**：item_links 12/17、near_dialog 5/6、resource_limits 7/10。残りはtkinterがなくて落ちる。
- **importできない**：capture_flow、evidence_retention、github_update、instance_guard（`WinDLL`）、karen_ui、notification（`winsound`）、updater、v11_settings。
- **非公開fixturesでskip**（12ファイル）：alt_display、alt_hold_simulation、glow_recovery、hud_filter、label_images、label_scale、local_ocr、overlap_detection、reward_samples、scroll_fragments、**tracker**、window_share。

`test_tracker`（`Store`・`StableReading`の中核テスト）は公開環境ではskipされる。保存と確定のロジックを直す時は、公開テストだけだと守りが薄い。
`docs/検証-v1.1.md`によれば、作者側の検証環境では全テスト221件が成功している。

## 8. 注意ゾーン
- **`drop_tool/app.py`**：829行。変更は小さく、新規ロジックは別モジュールへ。
- **認識の閾値**（0.92、0.035、`CENTER`、`MAX_FRAMES`、`consensus`の移動許容幅等）：非公開画像でしか回帰を確認できない。変更は事前に相談。
- **Windows依存**：`winsound`、`ctypes.WinDLL`。Linuxでは実行確認できない。
- **宝箱検知は試験機能**：未収集の角度や小さい箱は見逃す。オーブの全画面3枚は新旧とも未検出（`docs/検証-v1.1.md`）。
- **未精読の領域**：`updater.py`、`retention.py`、`csv_*`、`settings_views.py`は、docstringと関数一覧しか確認していない。直す時は最初に実コードを読み直すこと。
