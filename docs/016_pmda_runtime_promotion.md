# 016 レビュー済み候補の本番DB反映

## 目的
医学レビュー済み候補だけを拡張機能の軽量ランタイムDBへ反映する。

## 対象外
candidate状態の自動配信。

## 依存
015と医師・薬剤師によるレビュー完了。

## タスク
- [x] review CSVの承認・却下を候補DBへ取り込む
- [x] reviewedだけをランタイムDBへ変換する
- [x] 薬剤名マスターとの正規化対応を作成する
- [x] 既存手動シードとの差分レポートを生成する
- [x] 拡張機能のゴールデンテストを更新する

## レビューフロー

```powershell
.\.venv\Scripts\python.exe scripts\build_pmda_top20_db.py --source database --dataset-date <YYYY-MM-DD>
.\.venv\Scripts\python.exe scripts\top20_review.py export
# 医師・薬剤師が interactions.csv の review_decision、reviewer、reviewed_at、approval_id を記入
.\.venv\Scripts\python.exe scripts\top20_review.py import
.\.venv\Scripts\python.exe scripts\top20_review.py promote
```

抽出DBは`backend/data/top20_interactions.candidate.sqlite`、昇格済み実行DBは`backend/data/top20_interactions.sqlite`へ分離する。固定配布物へ含めるのは後者だけである。

- `review_decision`は`reviewed`または`rejected`とし、どちらにもレビュー者、タイムゾーン付きレビュー日時、承認IDを必須とする。
- CSVは全候補を一度ずつ含み、候補IDと内容ハッシュが抽出DBに一致しなければ取り込まない。
- `candidate`が1件でも残る場合、内容ハッシュが変わった場合、承認情報が欠ける場合は昇格しない。
- 昇格DBには`reviewed`行だけを収録し、`rejected`行は件数だけを監査metadataへ残す。
- `drug_master_mapping.csv`、`manual_seed_diff.csv`、`golden_results.draft.json`、`promotion_report.json`を生成する。薬剤名マスターに未対応の成分がある場合は既定で昇格DBを破棄する。
- 医学レビュー担当者はドラフトの全結果を確認し、`approval`へ実名、タイムゾーン付き日時、承認IDを記入して`golden_results.approved.json`とする。DBハッシュ、全対象・全成分の期待値、承認情報が一致しない製品bundleは生成できない。

## 現在の状態

技術的な取込・昇格経路と混入防止テストは完成している。実データのレビューCSVは未承認のため、現在同梱しているDBは昇格しておらず、製品版出荷ゲートは引き続き閉じている。

## 受入条件
出典、改訂年月、レビュー者、レビュー日時を欠く候補は本番判定に使われない。

## テスト
candidate、rejectedがランタイムDBへ混入しないことを確認する。
