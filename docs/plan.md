# クラリスロマイシン相互作用チェッカー開発計画

## 目的

院内利用を主対象として、入力された複数の処方薬・頻用OTC医薬品について、クラリスロマイシンを含む代表20成分との相互作用を確認するChrome拡張機能を提供する。

## 安全原則

- 最終判定はレビュー済みSQLiteレコードだけで行う。
- Ollamaは薬剤名候補とDB結果の要約だけに使用する。
- 曖昧一致は利用者が選択するまで判定しない。
- 「記載なし」は安全性の保証ではない旨を常時表示する。
- 入力内容と結果は保存しない。APIは`127.0.0.1`だけで起動する。
- シードDBはプロトタイプであり、臨床利用前に薬剤師等による最新版電子添文との照合を必須とする。

## 構成

- Chrome Manifest V3サイドパネル: TypeScript
- ローカルAPI: FastAPI、Pydantic
- DB: SQLite、レビュー可能なJSONシード
- LLM: Ollama、既定`qwen3.5:9b`

## API

- `GET /health`
- `GET /v1/dataset`
- `POST /v1/resolve`
- `POST /v1/check`
- `GET /v1/targets`

## 成功条件

- 一般名、商品名、規格付き名称、頻用OTCを複数入力できる。
- 完全一致以外は自動確定せず候補を表示する。
- OTC配合剤は全成分を評価し、最も重大な結果を代表表示する。
- Ollama停止時も辞書照合とDB判定が動作する。
- 出典、改訂情報、データ更新日を結果に表示する。
- 基準薬を代表20成分から選択し、双方の電子添文を直接名称で照合できる。

## データ源

- [PMDA 医療用医薬品情報検索](https://www.pmda.go.jp/PmdaSearch/iyakuSearch/)
- [PMDA OTC・要指導医薬品情報検索](https://www.pmda.go.jp/PmdaSearch/otcSearch/)
- [厚生労働省 薬価基準・一般名処方マスタ](https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000078916.html)
