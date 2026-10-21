# 開発案内 v1.1.7

Windows 64bit / Python 3.12。
`python -m pip install -r requirements.txt -r requirements-build.txt`

## 主な構成

- `app.py`：起動・自己診断・二重起動ガード。
- `drop_tool/app.py`：画面と読取フロー。
- `drop_tool/vision.py` / `label_scale.py`：品名領域・倍率補正（対応版のみ）。
- `drop_tool/tracker.py`：記録・学習・集計。保存形式はversion=1。
- `drop_tool/updater.py` / `update_view.py` / `update_helper.ps1`：更新取得・確認・適用・復旧。
- `assets/` / `references/` / `models/`：実行に必要な資産。

## テスト

`python tools/run_tests.py`（全量）

一部だけ回す時はテスト名を渡します：`python tools/run_tests.py test_learning test_item_links`。
モジュール名、`tests/test_x.py`のパス、`モジュール.クラス.メソッド`が使えます。読み込めない名前があれば実行せずに失敗します。

提供者の全画面画像は公開していないため、非公開画像に依存するモジュールはスキップを明示します。
元の配布前検証環境ではこれらを含めて試験しています。
提供画像を扱う場合もtests/fixturesとtools/benchmarks/videoはGit管理外のままにします。
既存の記録・設定を使用せず一時フォルダーで検証してください。

## ビルド

`python tools/build_exe.py dist`

`python tools/package_release.py dist/KarenDrop KarenDrop-v1.1.7-windows.zip`

`dist/KarenDrop/KarenDrop.exe --self-test result.json`

配布ZIPのdata・個人設定の混入を確認してください。既存LICENSEと第三者ライセンスを維持します。
更新は利用者のdata・除外設定を上書きしません。
ソース反映だけでは利用者へ配信されません。Release公開は配布ZIPと更新JSONを検証してから行います。

2026-10-19：非公開の提供画像を含む247テスト成功。宝箱の25枚は開発に使用した静止画であり独立評価ではありません。元画像・個人のdataは公開しません。

配布者向け手順・旧Drive初期登録JSONは開発資料としてのみ保持し、一般向けZIPには同梱しません。更新情報の作成には tools/package_release.py と drop_tool.updater.make_info を使います。

## SSL実装固有の配布データ

ビルド元のssl.pyがcodex-rejected-cas.pemを要求する環境では、tools/ssl_runtime.pyが同じ証明書データを凍結版sslの隣へ同梱します。信頼設定を除去せず保持し、必要ファイルが欠けたビルドは停止します。配布EXEの --self-test ではHTTPSコンテキストの生成も確認します。

`claude_workspace/`（Claude用の開発場所）はリリースに含めません。混入していると`tools/package_release.py`が停止します。詳細は`claude_workspace/RELEASE_RULES.md`を参照してください。
