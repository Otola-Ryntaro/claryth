# 001 プロジェクト基盤

## 目的
拡張機能、API、DB、テストの最小構成を用意する。

## 対象外
本番用データの医学的承認。

## 依存
なし。

## タスク
- [x] FastAPIパッケージ構成を作成する
- [x] SQLite初期化スクリプトを作成する
- [x] Manifest V3拡張機能構成を作成する
- [x] pytest構成を作成する

## 受入条件
API起動、拡張機能ビルド、テスト実行が再現できる。

## テスト
`python scripts/init_db.py`、`pytest`、`npm run build`を実行する。

