# くらりす 製品化・セキュリティレビュー

レビュー日: 2026-06-13

## エグゼクティブサマリー

現時点の判定は **製品版として出荷不可** です。コード品質の土台は良く、44件の自動テスト、拡張機能ビルド、`npm audit` はすべて成功しました。ループバック限定、Host制限、SQLパラメータ化、HTMLエスケープ、拡張機能CSP、LLMを判定に使わない設計も適切です。

一方、臨床結果を返すトップ20 DBが `pmda_extracted_review_required` のまま判定に使われ、DBには承認済みレコードだけを選別する列もありません。さらに、拡張機能とローカルAPIの相互認証がなく、同じユーザー権限の別プロセスが先にポート8765を確保すると、拡張機能へ偽の判定結果を返せます。これらは製品化を止める問題です。

現状で許容できる用途は、医師・薬剤師の臨床判断に使わない開発・デモ・非臨床評価です。

## 2026年6月13日 修正状況

- PR-001: 技術対策済み。未レビューDBは判定停止し、行単位レビューCSV、内容ハッシュ、承認メタデータ、`reviewed`行だけの昇格処理を追加した。実データの医学承認は未完了。
- SEC-001 / SEC-002: 修正済み。共有トークン、固定アプリID、プロトコル版、nonce、固定拡張Originを検証する。
- DATA-001: 修正済み。Ed25519署名manifest、SHA-256、SQLite完全性、スキーマ版、期限、承認情報を検証する。
- DEP-001 / VAL-001 / SEC-003 / UX-001 / A11Y-001: 実装修正済み。依存監査はPython・npmとも既知脆弱性0件。
- OPS-001: 配布署名、SBOM、更新・緊急停止・ロールバック手順は実装済み。実名責任者、法務確認、クリーンWindows 10/11実機E2Eは未完了。

したがって、重大なコード上の指摘は修正したが、医学承認と運用・実機承認が残るため、最終判定は引き続き**製品版として出荷不可**である。

再検証ではPython 82件、拡張UI 5件、TypeScriptビルドが成功し、`pip-audit --strict`と`npm audit --audit-level=high`はいずれも既知脆弱性0件だった。評価版固定bundleは署名、全収録ファイルハッシュ、公開鍵fingerprintを検証し、秘密鍵・認証トークン・原XML/PDF/CSVが含まれないことを確認した。

## High

### PR-001: 医学レビュー前のトップ20データが臨床的な判定結果として表示される

- 場所: `README.md:70-72`, `README.md:89`, `backend/app/top20.py:24-25`, `backend/app/top20.py:249-341`, `backend/app/main.py:206-217`
- 証拠: READMEはトップ20 DBを医学レビュー前と明記しています。実DBの `review_status` は `pmda_extracted_review_required`、相互作用43,235件に承認・レビュー・検証状態の列はありません。しかしAPIはDBファイルが存在するだけで利用可能とし、全レコードから `contraindicated` / `caution` を返します。
- 影響: 抽出誤り、文書選択誤り、製剤・投与経路の取り違えが、そのまま医療者向けの判定として表示される可能性があります。
- 修正: レコード単位のレビュー状態、レビュー者、レビュー日時、原資料版、承認署名を保持し、`approved` 以外をランタイムDBへ入れないでください。起動時にも承認済みデータセットでなければ `/v1/check` を503で停止する必要があります。
- 補足: `README.md:89` の「医学レビュー前に画面判定用DBへ反映しない設計」と現在の実装・実DBは一致していません。

### SEC-001: ポート8765上の別プロセスを正規APIと誤認できる

- 場所: `scripts/clarith_launcher.ps1:44-53`, `extension/src/sidepanel.ts:55-68`, `extension/src/manifest.json:7`
- 証拠: ランチャーはポート8765に何かがListenしていれば起動を中止します。拡張機能は `http://127.0.0.1:8765` の応答を共有秘密や署名なしで信用します。
- 影響: 同一ユーザーで動く別アプリやマルウェアが先に8765を確保し、偽の「併用禁忌」「記載なし」や偽リンクを返せます。
- 修正: インストール時にランダムな共有トークンを生成し、拡張機能の専用ヘッダーとAPI側で照合してください。`/health` には固定アプリID、プロトコル版、起動時nonceを返し、ランチャーもTCP接続ではなく認証済みhealth応答を検証してください。

### DATA-001: DBの完全性・真正性・承認状態を起動時に検証しない

- 場所: `backend/app/database.py:109-111`, `backend/app/top20.py:24-25`, `backend/app/main.py:33-36`, `backend/app/main.py:68-85`
- 証拠: 通常DBは存在確認、トップ20 DBも存在確認だけです。現在のファイルはSQLite `integrity_check=ok` でしたが、期待ハッシュ、署名、スキーマ版、承認済み状態、許容データ日付を起動時に強制していません。
- 影響: 破損、取り違え、古いDB、改変DBを「DB接続済み」と表示し、医療結果へ使う可能性があります。
- 修正: 署名済みリリースmanifestにDBのSHA-256、スキーマ版、データ版、PMDA取得日、承認状態を記録し、起動時に全項目と `PRAGMA integrity_check` を検証してください。

### OPS-001: 配布・更新・責任分界が製品運用に達していない

- 場所: `docs/010_distribution_and_updates.md:16-18`, `docs/009_validation.md:17`, `pyproject.toml:6-15`
- 証拠: 変更管理責任者、更新頻度、データ再配布条件、リリース署名、SBOM、薬剤師承認済み全レコードのゴールデンテストが未完了です。Python依存も範囲指定だけで、再現可能なロックとハッシュがありません。
- 影響: 施設ごとに異なる依存・DBが配布され、誰がいつ承認した版か追跡できず、脆弱性対応やロールバックも保証できません。
- 修正: 署名済みインストーラまたは固定配布物、Pythonロックファイル、SBOM、リリース承認票、更新・緊急停止・ロールバック手順を製品ゲートにしてください。

## Medium

### SEC-002: 任意のChrome拡張Originを許可し、APIにクライアント認証がない

- 場所: `backend/app/main.py:44-65`
- 証拠: `chrome-extension` スキームなら拡張IDを問わず許可し、CORSも `allow_origins=["*"]` です。実測で `Origin: chrome-extension://attackerextensionid` に対し `/v1/dataset` は200、`Access-Control-Allow-Origin: *` を返しました。
- 影響: 悪意ある拡張機能がAPIを呼び出し、CPU/GPUを使うOllama warmupや名前解決を繰り返せます。Origin制限は認証の代替になりません。
- 修正: SEC-001の共有トークンを全APIへ必須化し、可能なら固定された正規拡張IDだけを許可してください。CORSは必要なOriginとヘッダーだけに限定してください。

### DEP-001: インストール済みStarlette 0.46.2に既知アドバイザリがある

- 場所: 実行環境の `starlette==0.46.2`, `pyproject.toml:7`
- 証拠: PyPI/OSVは0.46.2にCVE-2025-54121、CVE-2025-62727、2026年のHost検証問題を掲載しています。現在のアプリはmultipart、`FileResponse`、`request.url` による認可を使わず、`TrustedHostMiddleware` もあるため、確認したコードでの直接悪用可能性は低いです。
- 影響: 未使用経路でも脆弱な依存を製品に含め続け、将来の機能追加で露出するおそれがあります。
- 修正: 最新FastAPI/Starlette互換系へ更新し、ロック後にテストしてください。CIへPython依存監査を追加してください。
- 参照: https://pypi.org/pypi/starlette/0.46.2/json

### VAL-001: リクエスト総量と一部文字列に上限がない

- 場所: `backend/app/models.py:19-28`, `backend/app/models.py:53-60`, `backend/app/__main__.py:8-9`
- 証拠: `text` は4,000文字、配列は20件に制限されていますが、`inputs` の各文字列、`CheckItem.input_name`、`drug_id`、`target_id` は無制限です。ASGI層にもリクエストボディ上限やレート制限がありません。
- 影響: ローカルの悪意ある拡張・プロセスから大きなJSONや連続リクエストを送り、メモリ・CPUを消費できます。
- 修正: 文字列ごとの `max_length`、`extra="forbid"`、全体ボディ上限、軽量なレート制限または同時実行制限を追加してください。

### UX-001: 未レビュー状態が小さな生コード表示だけで、利用を止めない

- 場所: `extension/src/sidepanel.ts:177-193`, `extension/src/sidepanel.css:101`, `extension/src/sidepanel.html:110-113`
- 証拠: `pmda_extracted_review_required` は画面下部の9pxテキストへそのまま表示されます。判定ボタンは無効化されず、承認状態を日本語で説明する警告や確認もありません。
- 影響: 利用者がレビュー未完了を見落とし、完成済みデータと誤認する可能性があります。
- 修正: 未承認時は画面上部に常時表示の強い警告を出し、臨床判定を無効化してください。状態コードではなく「医学レビュー未完了・臨床利用禁止」と表示してください。

## Low

### SEC-003: ローカルAPIのSwagger/OpenAPIが常時有効

- 場所: `backend/app/main.py:39`
- 証拠: 実測で `/docs` は200でした。
- 影響: ローカル攻撃者にAPI一覧と試行UIを提供します。単独で重大な問題ではありません。
- 修正: 製品モードでは `docs_url=None`, `redoc_url=None`, `openapi_url=None` としてください。

### A11Y-001: 重要情報を含む文字サイズが9px中心

- 場所: `extension/src/sidepanel.css:32`, `extension/src/sidepanel.css:45`, `extension/src/sidepanel.css:54`, `extension/src/sidepanel.css:87`, `extension/src/sidepanel.css:97-101`
- 証拠: レビュー状態、重大度バッジ、根拠詳細、フッターが9pxです。
- 影響: 高齢者や視力の弱い利用者、拡大率が低い環境で重要情報を読み落としやすくなります。
- 修正: 重要情報は少なくとも12px相当を基準にし、200%ズーム、キーボード操作、Windows高コントラストで確認してください。

## 良い点

- APIは `127.0.0.1` 固定で、`TrustedHostMiddleware` も設定されています。
- SQLはユーザー入力をパラメータ化しており、確認範囲でSQLインジェクションは見つかりませんでした。
- 根拠HTMLは `html.escape` と厳しいCSPを使っています。
- 拡張機能は結果表示に `textContent` を使い、`innerHTML` を使っていません。
- Manifest権限は `sidePanel` とループバックhostだけで、過剰なタブ・閲覧履歴権限がありません。
- LLMは既定オフで、候補提示に限定され、相互作用の判定・説明生成には使われません。
- 根拠ページは電子添文節、改訂年月、原文、PMDA PDFリンクが明確で、目視確認したワルファリン例は読みやすい構成でした。

## 実施した検証

- `python -m pytest`: 44件成功。
- `npm run build`: 成功。
- `npm audit --json`: 0件。
- SQLite `PRAGMA integrity_check`: `ok`。
- API health: 通常DB `prototype_manual_review_required`、トップ20 DB `pmda_extracted_review_required`。
- 実APIでワルファリン × クラリスロマイシンの併用注意、根拠節10.2、改訂2026-04、PMDA PDFリンクを確認。
- 根拠HTMLをブラウザで目視し、表示崩れや明白なXSS出力は確認されませんでした。
- 制約: Chrome拡張のサイドパネル自体は、ブラウザのローカルファイル/拡張URL制限により実操作できず、HTML/CSS/TypeScriptの静的レビューに留まりました。

## 製品版の必須ゲート

1. 医師・薬剤師が承認したレコードだけを含む署名済みDBを作り、未承認DBでは判定APIを停止する。
2. 拡張機能とAPIを共有トークン・アプリID・nonceで相互確認し、ポート先取りによる偽APIを排除する。
3. DBハッシュ、スキーマ版、データ日、承認者、依存ロック、SBOMを含む署名済みリリースを作る。
4. 更新責任者、PMDA更新頻度、緊急停止、ロールバック、監査記録を定める。
5. 承認済み全レコードのゴールデンテスト、クリーンPC導入試験、Chrome実機E2E、アクセシビリティ試験を完了する。

この5項目が完了するまでは、「医療者向け製品」ではなく「臨床利用禁止の評価版」として扱うのが妥当です。
