# くらりす

**く**すりの **ら**くな **リ**スク **ス**クリーニング、略して「くらりす」です。

クラリスロマイシンを含む「相互作用検索が複雑な代表20成分」と、複数の処方薬・OTC医薬品との相互作用を確認する、医療者・院内利用向けのChrome拡張機能です。判定APIとデータベースはPC内で動作し、Ollamaは任意の薬剤名候補補助としてだけ利用できます。

> [!WARNING]
> 本ツールは医療判断を代替しません。「記載なし」は相互作用がないことの保証ではありません。必ず最新の電子添文、患者背景、用量、腎・肝機能を確認してください。

## 主な機能

- 一般名、販売名、頻用OTC商品名を最大20件まとめて入力
- 基準薬をトップ20から選択。既定はクラリスロマイシン
- 選択薬側と入力薬側のPMDA電子添文10.1・10.2を双方向に直接名称照合
- 表記揺れや軽微な誤字から候補を提示し、利用者が薬剤を確定
- `併用禁忌`、`併用注意`、`確認資料上の記載なし`などを薬剤ごとに表示
- 該当相互作用行をローカル根拠ページで即表示し、PMDA電子添文PDFへ直接移動
- SQLiteの構造化データだけで相互作用を判定
- 標準動作はLLMなし。Ollamaは辞書で未解決の薬剤名候補提示だけを任意で補助
- 相互作用、重大度、根拠、説明はLLMで生成せず、SQLiteの収載内容だけを表示
- APIは`127.0.0.1:8765`、Ollamaは`127.0.0.1:11434`だけを使用

## はじめる

詳しい画面操作やトラブル対応は[初心者向けユーザーガイド](docs/user_guide.md)を参照してください。

Windows PowerShellでプロジェクトフォルダを開き、次を順に実行します。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .

cd extension
npm install
npm run build
cd ..

.\.venv\Scripts\python.exe scripts\init_db.py
.\.venv\Scripts\python.exe scripts\build_pmda_top20_db.py --source database --dataset-date 2026-06-12
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_windows_launcher.ps1
```

Chromeで`chrome://extensions`を開き、デベロッパーモードを有効にして、`extension/dist`を「パッケージ化されていない拡張機能」として読み込みます。その後、「くらりす」のサイドパネルで「判定APIを起動」を押します。

AI薬剤名補助を使う場合だけ、別途Ollamaを導入して`ollama pull qwen3.5:9b`を実行し、サイドパネルの「AI薬剤名補助を使う」をオンにします。オフの場合、OllamaへのHTTP通信は行いません。

## データの取得元と取得日

### 現在の画面判定用データ

- ファイル: `backend/data/seed.json`
- データ版: `0.1.1-prototype`
- 作成・確認日: **2026年6月12日**
- 参照元:
  - [PMDA 医療用医薬品 情報検索](https://www.pmda.go.jp/PmdaSearch/iyakuSearch/)
  - [PMDA 一般用医薬品・要指導医薬品 情報検索](https://www.pmda.go.jp/PmdaSearch/otcSearch/)
- 状態: `prototype_manual_review_required`

これは開発・動作確認用の限定的な手動シードです。PMDA全件抽出結果を自動反映した本番データではありません。

### PMDA全件抽出用データ

- 取得元: [PMDA「医療用医薬品添付文書一括ダウンロードサービス」](https://www.pmda.go.jp/safety/info-services/medi-navi/0012.html)
- 取得方法: 利用者がサービスから**SGML/XMLを手動ダウンロード**し、`database`へ展開
- ローカル取得・展開日: **2026年6月12日**
- DB構築日: **2026年6月12日**
- 対象: XML 17,737ファイル、内容重複除外後11,245文書
- 解析結果: クラリスロマイシン含有26文書、解析エラー0文書
- 出力: `backend/data/pmda_clarith.sqlite`および`artifacts/pmda_clarith/`
- 状態: すべて`candidate`。医師・薬剤師によるレビュー前

トップ20検索では同じPMDA XMLから`backend/data/top20_interactions.sqlite`を構築します。2026年6月12日の構築結果は、一般名3,954件、別名15,527件、10.1・10.2行43,235件です。このDBも`pmda_extracted_review_required`であり、医学レビュー済みを意味しません。

取得日はローカルファイルの取得記録とDBの`source_coverage`に基づきます。個々の電子添文の改訂年月は文書ごとに保持しています。詳細は[抽出レポート](docs/pmda_clarith_extraction_report_20260612.md)を参照してください。

PMDA検索画面の自動巡回は行いません。PMDAは検索ページの自動巡回ダウンロードを認めていないため、一括ダウンロードサービスから手動取得したファイルだけを処理します。

## PMDAデータの再構築

`database`に手動取得したPMDA XMLを配置後、次を実行します。

```powershell
.\.venv\Scripts\python.exe scripts\build_pmda_clarith_db.py --source database --dataset-date 2026-06-12
.\.venv\Scripts\python.exe scripts\validate_pmda_clarith_db.py
.\.venv\Scripts\python.exe scripts\export_pmda_clarith_review.py
.\.venv\Scripts\python.exe scripts\build_pmda_top20_db.py --source database --dataset-date 2026-06-12
```

抽出候補は医学レビュー前に画面判定用DBへ反映しない設計です。

## トップ20検索の制約

- リスト中の薬剤群を一括判定せず、各順位から具体的な代表20成分を選択肢にしています。
- 同じ薬効群でも成分ごとに結果が異なるため、プルダウンに表示された成分だけが基準薬です。
- 現在は電子添文10.1・10.2の**直接名称**を双方向照合します。薬効群名だけの記載や患者条件からの推論は自動確定しません。
- タクロリムスとロキソプロフェンの基準薬文書は全身投与・内服製剤に限定し、外用剤を除外しています。
- 「記載なし」は直接名称を確認できなかったという意味で、安全性の保証ではありません。
- 根拠ページは取得済み電子添文から抽出した10.1・10.2の該当行です。最終確認は併記されたPMDA電子添文PDFで行います。

## トップ20成分の選定根拠

基準薬となる代表20成分は、①併用禁忌の多さ、②CYP/P-gp/OATPなど機序の複雑さ、③出血・不整脈・中毒など重症化のしやすさ、④腎機能・用量・商品名で判断が変わる度合い、を基準に選定しています。各成分の選定理由・代表的な相互作用・出典は[トップ20成分の選定根拠](docs/top20_selection_rationale.md)にまとめています（各成分のID・順位の定義は[017_top20_scope_and_targets.md](docs/017_top20_scope_and_targets.md)）。

## 構成

- `backend/`: FastAPI、SQLite、薬剤名解決、相互作用判定
- `extension/`: Chrome Manifest V3サイドパネル
- `pmda_builder/`: PMDA XMLの解析と候補DB構築
- `scripts/`: 初期化、起動、PMDA抽出用コマンド
- `docs/`: 計画、チケット、ユーザーガイド、抽出レポート

## プライバシー

入力はローカルAPIへ送信され、外部LLMには送信されません。AI補助を有効にした場合だけ、未解決の薬剤名とDB内候補がローカルOllamaへ送られます。患者氏名、ID、生年月日などの患者情報は入力しないでください。入力履歴を保存する機能はありません。

## ライセンス

ソースコードは[MIT License](LICENSE)で公開します。

Copyright (c) 2026 [音良林太郎](https://x.com/Otola_ryntaro)

PMDA電子添文など第三者が権利を持つ原資料・抽出データにはMIT Licenseを適用しません。PMDAの[添付文書等情報検索ページご利用上の注意](https://www.pmda.go.jp/searchhelp_005.html)と各権利者の条件に従ってください。原XML、生成SQLite、レビューCSVはGit管理対象外です。
