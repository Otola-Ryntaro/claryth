# くらりす

現在のアプリバージョンは`0.2.0`です。変更内容は[CHANGELOG](CHANGELOG.md)を参照してください。

**く**すりの **ら**くな **リ**スク **ス**クリーニング、略して「くらりす」です。

クラリスロマイシンなど相互作用確認が少し面倒な薬を基準に、複数の処方薬・OTC医薬品との組み合わせをローカルで調べるためのChrome拡張です。FastAPIとSQLiteをPC内で動かし、薬剤名候補の補助だけ任意でOllamaを使えます。

> [!WARNING]
> このツールは医療判断を代替しません。「記載なし」は相互作用がないことの保証ではありません。実際の判断では、必ず最新の電子添文、患者背景、用量、腎・肝機能などを確認してください。

> [!IMPORTANT]
> 個人開発の実験的なオープンソース公開です。品質・正確性・最新性は保証しません。診断・治療・処方の判断根拠として使わないでください。利用は自己責任でお願いします（[LICENSE](LICENSE)の無保証条項に従います）。

## 主な機能

- 一般名、販売名、頻用OTC商品名を最大20件まとめて入力
- 基準薬をトップ20から選択。既定はクラリスロマイシン
- 選択薬側と入力薬側のPMDA電子添文10.1・10.2を双方向に直接名称照合
- 表記揺れや軽微な誤字から候補を提示し、利用者が薬剤を確定
- `併用禁忌`、`併用注意`、`確認資料上の記載なし`などを薬剤ごとに表示
- 該当行をローカル根拠ページで表示し、PMDA電子添文PDFへ移動
- 相互作用、重大度、根拠、説明はLLMで生成せず、SQLiteの収載内容だけを表示
- 標準動作はLLMなし。Ollamaは薬剤名候補の補助だけに使用
- APIは`127.0.0.1:8765`、Ollamaは`127.0.0.1:11434`だけを使用
- 拡張機能とAPIはユーザー単位の共有トークンで接続
- 起動時に署名、DBハッシュ、SQLite完全性、スキーマ版、有効期限を確認

## はじめる

詳しい画面操作やトラブル対応は[初心者向けユーザーガイド](docs/user_guide.md)を参照してください。

Windows PowerShellでプロジェクトフォルダを開き、同梱DBをそのまま使う場合は次を実行します。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_release.ps1
```

その後、Chromeで`chrome://extensions`を開き、デベロッパーモードを有効にして、生成された`extension/dist`を「パッケージ化されていない拡張機能」として読み込みます。サイドパネルで「判定APIを起動」を押すと、このPC用のローカルAPI認証情報を自動取得します。`dist`にはAPIトークンを保存しません。

同梱DBは動作確認用です。データ状態、署名、期限、DB変更などに問題がある場合、画面上部に理由が表示され、相互作用判定は停止します。

## ローカル開発

PMDA XMLからDBを作り直す場合は、PMDAの一括ダウンロードサービスから取得したSGML/XMLを`database`へ展開してから実行します。

```powershell
python -m pip install uv==0.11.21
uv sync --locked --extra test

cd extension
npm ci
cd ..

.\.venv\Scripts\python.exe scripts\init_db.py
.\.venv\Scripts\python.exe scripts\build_pmda_top20_db.py --source database --dataset-date 2026-06-12
$expiresAt = (Get-Date).ToUniversalTime().AddDays(30).ToString("o")
$manifestId = "local-$((Get-Date).ToString('yyyyMMdd-HHmmss'))"
.\.venv\Scripts\python.exe scripts\generate_release_signing_key.py --force
.\.venv\Scripts\python.exe scripts\sign_release_manifest.py --expires-at $expiresAt --manifest-id $manifestId
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_windows_launcher.ps1
```

ローカルでAPI仕様画面が必要な場合だけ、起動前に次を設定します。通常起動では`/docs`、`/redoc`、`/openapi.json`を公開しません。

```powershell
$env:CLARITH_MODE = "development"
```

AI薬剤名補助を使う場合は、別途Ollamaを導入してモデルを取得し、サイドパネルの「AI薬剤名補助を使う」をオンにします。オフの場合、OllamaへのHTTP通信は行いません。

```powershell
ollama pull qwen3.5:9b
```

## データ

### 同梱の動作確認用データ

- ファイル: `backend/data/seed.json`
- データ版: `0.1.1-prototype`
- 作成・確認日: **2026年6月12日**
- 参照元:
  - [PMDA 医療用医薬品 情報検索](https://www.pmda.go.jp/PmdaSearch/iyakuSearch/)
  - [PMDA 一般用医薬品・要指導医薬品 情報検索](https://www.pmda.go.jp/PmdaSearch/otcSearch/)

これは開発・動作確認用の限定的な手動シードです。PMDA全件抽出結果を自動反映したデータではありません。

### PMDA全件抽出用データ

- 取得元: [PMDA「医療用医薬品添付文書一括ダウンロードサービス」](https://www.pmda.go.jp/safety/info-services/medi-navi/0012.html)
- 取得方法: 利用者がサービスから**SGML/XMLを手動ダウンロード**し、`database`へ展開
- ローカル取得・展開日: **2026年6月12日**
- DB構築日: **2026年6月12日**
- 対象: XML 17,737ファイル、内容重複除外後11,245文書
- 解析結果: クラリスロマイシン含有26文書、解析エラー0文書
- 出力: `backend/data/pmda_clarith.sqlite`および`artifacts/pmda_clarith/`

トップ20検索では同じPMDA XMLから`backend/data/top20_interactions.sqlite`を構築します。2026年6月12日の構築結果は、一般名3,954件、別名15,527件、10.1・10.2行43,235件です。

取得日はローカルファイルの取得記録とDBの`source_coverage`に基づきます。個々の電子添文の改訂年月は文書ごとに保持しています。詳細は[抽出レポート](docs/pmda_clarith_extraction_report_20260612.md)を参照してください。

PMDA検索画面の自動巡回は行いません。PMDAは検索ページの自動巡回ダウンロードを認めていないため、一括ダウンロードサービスから手動取得したファイルだけを処理します。

## PMDAデータの再構築

`database`に手動取得したPMDA XMLを配置後、次を実行します。

```powershell
.\.venv\Scripts\python.exe scripts\build_pmda_clarith_db.py --source database --dataset-date 2026-06-12
.\.venv\Scripts\python.exe scripts\validate_pmda_clarith_db.py
.\.venv\Scripts\python.exe scripts\build_pmda_top20_db.py --source database --dataset-date 2026-06-12
```

DBを再構築したら、manifestの再署名も必要です。

```powershell
$expiresAt = (Get-Date).ToUniversalTime().AddDays(30).ToString("o")
$manifestId = "local-$((Get-Date).ToString('yyyyMMdd-HHmmss'))"
.\.venv\Scripts\python.exe scripts\sign_release_manifest.py --expires-at $expiresAt --manifest-id $manifestId
```

## トップ20検索の制約

- リスト中の薬剤群を一括判定せず、各順位から具体的な代表20成分を選択肢にしています。
- 同じ薬効群でも成分ごとに結果が異なるため、プルダウンに表示された成分だけが基準薬です。
- 現在は電子添文10.1・10.2の**直接名称**を双方向照合します。薬効群名だけの記載や患者条件からの推論は自動確定しません。
- タクロリムスとロキソプロフェンの基準薬文書は全身投与・内服製剤に限定し、外用剤を除外しています。
- 「記載なし」は直接名称を確認できなかったという意味で、安全性の保証ではありません。
- 根拠ページは取得済み電子添文から抽出した10.1・10.2の該当行です。最終確認は併記されたPMDA電子添文PDFで行います。

## トップ20成分の選定根拠

基準薬となる代表20成分は、併用禁忌の多さ、CYP/P-gp/OATPなど機序の複雑さ、出血・不整脈・中毒など重症化のしやすさ、腎機能・用量・商品名で判断が変わる度合いを基準に選定しています。各成分の選定理由・代表的な相互作用・出典は[トップ20成分の選定根拠](docs/top20_selection_rationale.md)にまとめています。

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

PMDA電子添文など第三者が権利を持つ原資料・抽出データにはMIT Licenseを適用しません。PMDAの[添付文書等情報検索ページご利用上の注意](https://www.pmda.go.jp/searchhelp_005.html)と各権利者の条件に従ってください。公開repoにはアプリ実行に必要な評価用SQLite DB、`release_manifest.json`、`release_manifest.sig`を同梱します。原XML、候補DB、作業用エクスポートはGit管理対象外です。
