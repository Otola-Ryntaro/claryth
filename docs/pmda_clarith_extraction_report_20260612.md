# PMDAクラリスロマイシン相互作用抽出レポート

## 実行概要

- 実行日: 2026-06-12
- 入力: `database`配下のPMDA XML 17,737ファイル
- 内容重複除外後: 11,245文書
- XML解析エラー: 0文書
- クラリスロマイシン含有文書: 26文書
- 単剤文書: 24文書
- クラリス含有配合パック: 2文書

## 抽出結果

- 単剤文書由来の一次候補: 720行
- 一次候補の完全同一文面集約: 62行
- 一次候補の併用禁忌: 408行
- 一次候補の併用注意: 312行
- 配合パック由来の補足候補: 80行
- 相手薬添付文書側の直接記載: 531行

完全同一文面集約の62行は薬剤数ではない。句読点、改行、表記差が残るため、薬剤名マスターへの正規化と医学レビューが必要である。

## 成果物

- SQLite: `backend/data/pmda_clarith.sqlite`
- 対象文書一覧: `artifacts/pmda_clarith/clarithromycin_documents.csv`
- 単剤一次候補: `artifacts/pmda_clarith/primary_candidates.csv`
- 一次候補集約: `artifacts/pmda_clarith/primary_candidates_consolidated.csv`
- 配合パック補足候補: `artifacts/pmda_clarith/supplemental_combination_candidates.csv`
- 相手薬側の逆引き: `artifacts/pmda_clarith/reverse_hits.csv`
- 件数とカバレッジ: `artifacts/pmda_clarith/summary.json`

## 安全上の扱い

全レコードの状態は`candidate`であり、拡張機能の本番判定DBには反映していない。クラリス含有配合パックは他成分由来の相互作用が混在するため、一次候補から分離した。医師・薬剤師による承認後に限り、チケット016でランタイムDBへ反映する。
