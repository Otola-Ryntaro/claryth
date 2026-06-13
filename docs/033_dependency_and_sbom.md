# 033 依存固定・脆弱性監査・SBOM

## 目的
再現可能で監査可能な依存セットを作り、既知脆弱性を含むリリースを防ぐ。

## 対象外
アプリ固有の脆弱性修正と医学データ承認。

## 依存
032と並行可能。035の前提。

## タスク
- [x] FastAPI、Starlette、Uvicornを互換性のある修正版へ更新する
- [x] Python依存をハッシュ付きロックファイルへ固定する
- [x] npm依存の再現可能インストールを`npm ci`へ統一する
- [x] Pythonとnpmの依存監査をCIへ追加する
- [x] CycloneDXまたはSPDX形式のSBOMを生成する
- [x] 脆弱性例外の期限、理由、承認者を記録する

## 受入条件
クリーン環境で同じ依存が再現され、High以上の未承認脆弱性がない。

## テスト
ロックファイルだけからセットアップし、全テスト、ビルド、依存監査を実行する。

## 実装メモ
- Pythonは`uv==0.11.21`と`uv.lock`を使用し、直接依存と全配布ファイルのSHA-256を固定する。
- 直接依存は2026年6月13日時点の公式PyPI最新版へ固定する。
- CIはWindows、Python 3.13、Node.js 22で`uv sync --locked`と`npm ci`を実行する。
- Python監査は`pip-audit --strict`、Node監査は`npm audit --audit-level=high`を使用する。
- SBOMはPythonとChrome拡張をそれぞれCycloneDX JSONとして`artifacts/sbom`へ生成し、CI artifactとして保存する。
- 例外は`security/vulnerability_exceptions.json`へ理由、承認者、期限を必須記録し、期限切れはCIを失敗させる。現在の例外は0件。

## 検証状況
- `uv.lock`から75パッケージをクリーン同期し、警告なしでPython全82テスト成功。
- `pip-audit --strict`は例外0件で既知脆弱性なし。
- `npm ci`、拡張ビルド、`npm audit --audit-level=high`は成功し、既知脆弱性0件。
- PythonとChrome拡張のCycloneDX 1.5 JSONを実生成済み。
