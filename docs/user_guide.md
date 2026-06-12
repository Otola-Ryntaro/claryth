# くらりす 初心者向けユーザーガイド

## 1. このツールでできること

「くらりす」は、**く**すりの **ら**くな **リス**ク スクリーニングを由来とする名称です。入力した処方薬やOTC医薬品と、プルダウンで選択した代表20成分との相互作用を確認します。既定の基準薬はクラリスロマイシンです。

判定と通常の薬剤名検索はPC内のSQLiteデータベースとRapidFuzzが行います。Ollamaは任意機能で、辞書では候補が見つからない誤字や略称について、DB内候補を最大3件に絞るためだけに使われます。

## 2. 必要なもの

- Windows 10またはWindows 11
- Google Chrome
- Python 3.11以上
- Node.jsとnpm
- このプロジェクト一式

Ollamaは必須ではありません。AI薬剤名補助を使う場合だけ、[Windows版公式ページ](https://ollama.com/download/windows)から導入します。

## 3. 初回セットアップ

### 3.1 PowerShellを開く

エクスプローラーで「くらりす」のプロジェクトフォルダを開き、アドレスバーへ`powershell`と入力してEnterキーを押します。

### 3.2 Python環境を準備する

以下を1行ずつ実行します。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

### 3.3 Chrome拡張機能をビルドする

```powershell
cd extension
npm install
npm run build
cd ..
```

### 3.4 任意: Ollamaモデルを導入する

通常利用ではこの手順を飛ばせます。AI薬剤名補助を使う場合の既定モデルは`qwen3.5:9b`です。

```powershell
ollama pull qwen3.5:9b
```

別モデルを使う場合は、API起動前に環境変数`CLARITH_OLLAMA_MODEL`を設定します。

### 3.5 判定DBを初期化する

```powershell
.\.venv\Scripts\python.exe scripts\init_db.py
.\.venv\Scripts\python.exe scripts\build_pmda_top20_db.py --source database --dataset-date 2026-06-12
```

### 3.6 サイドパネルから起動できるようにする

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\install_windows_launcher.ps1
```

これは現在のWindowsユーザーへ`clarith://`ランチャーを登録します。管理者権限は不要です。

### 3.7 Chromeへ読み込む

1. Chromeで`chrome://extensions`を開きます。
2. 右上の「デベロッパーモード」をオンにします。
3. 「パッケージ化されていない拡張機能を読み込む」を押します。
4. `extension/dist`フォルダを選択します。
5. 拡張機能メニューから「くらりす」を固定します。

## 4. 毎回の使い方

1. Chromeの「くらりす」アイコンを押してサイドパネルを開きます。
2. 「判定APIを起動」を押します。
3. Chromeが外部アプリを開く確認を表示したら、`くらりす Local Launcher`を許可します。
4. 状態が「DB接続済み」になるまで待ちます。
5. 画面最上部で相互作用を調べる基準薬を選びます。
6. 確認したい併用薬を1行に1件ずつ入力します。
7. 「相互作用を確認」を押します。
8. 薬剤候補が表示された場合は、正しいものを選択して判定します。

入力例：

```text
デエビゴ
アレグラ
バイアスピリン
```

改行のほか、読点やカンマでも区切れます。最大20件です。患者氏名や患者IDは入力しないでください。

## 5. 結果の読み方

- `併用禁忌`: 原則として併用しない組み合わせ
- `併用注意`: 観察、用量調整、代替薬検討などが必要な可能性がある組み合わせ
- `記載なし`: 現在の確認資料では記載を確認できなかった状態。安全の保証ではない
- `要確認`: 薬剤名を一意に確定できず、候補選択が必要
- `未収載`: 現在の薬剤マスターにない
- `システムエラー`: APIまたはDBで障害が発生

カードの「根拠と詳細を表示」を開くと、機序、対応、データ更新日、出典を確認できます。「該当相互作用をすぐ表示」は抽出済みの10.1・10.2該当行を新しいタブへ直接表示し、「PMDA電子添文PDFを開く」は検索画面を経由せず原資料を開きます。

トップ20の選択肢は薬剤群全体ではなく代表成分です。例えばDOACの選択肢はアピキサバンであり、他のDOACを同じ結果として扱いません。現在の検索は双方の電子添文10.1・10.2にある直接名称を照合します。

## 6. AI薬剤名補助

「AI薬剤名補助を使う」は初期状態でオフです。オフのままでも、一般名、販売名、規格付き名称、全半角、軽微な誤字候補と相互作用判定を利用できます。

オンにした場合だけOllamaの状態、起動、モデル読込ボタンが表示されます。AI候補は必ず「AI候補・要確認」となり、利用者が候補を選ぶまで相互作用判定へ進みません。AIは相互作用、重大度、根拠、説明を生成しません。

## 7. よくある問題

### 「ローカルAPIを起動してください」と表示される

「判定APIを起動」を押し、外部アプリの確認を許可してください。改善しない場合はPowerShellで手動起動します。

```powershell
.\.venv\Scripts\python.exe -m backend.app
```

### 「signal timed out」または時間切れになる

1. 「再確認」を押します。
2. AI薬剤名補助をオフにして再試行します。
3. `http://127.0.0.1:8765/health`をChromeで開き、API応答を確認します。
4. `.runtime/api.err.log`と`.runtime/ollama.err.log`を確認します。

### Ollamaまたはモデルが未導入と表示される

AI薬剤名補助を使わない場合は対応不要です。通常のDB判定をそのまま利用できます。AI補助を使う場合は次を実行します。

```powershell
ollama serve
ollama pull qwen3.5:9b
ollama ls
```

`ollama serve`は起動したままにし、別のPowerShellで残りのコマンドを実行します。

### 拡張機能を変更したのに画面へ反映されない

```powershell
cd extension
npm run build
cd ..
```

その後、`chrome://extensions`の「くらりす」欄にある再読み込みボタンを押します。

## 8. 更新と安全確認

- 画面下部でデータ版とレビュー状態を確認してください。
- 臨床利用前に施設の責任者または薬剤師がデータを承認してください。
- 常にPMDAの最新電子添文も確認してください。
- PMDA全件抽出候補はレビュー前のため、現在の画面判定へ自動反映されません。

## 9. アンインストール

Chromeの拡張機能管理画面から「くらりす」を削除します。Windowsランチャーの登録は次で削除できます。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\uninstall_windows_launcher.ps1
```
