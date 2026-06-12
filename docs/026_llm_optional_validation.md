# 026 LLM任意化検証と文書

## 目的
LLMなしを標準構成として検証し、READMEとユーザーガイドへ反映する。

## 対象外
LM Studio、クラウドLLM、Native Messaging。

## 依存
022〜025。

## タスク
- [x] OllamaなしのAPI・トップ20・名称解決・判定を検証する
- [x] AI補助OFF時にOllama通信が発生しないことを検証する
- [x] Python全テストとTypeScriptビルドを実行する
- [x] READMEと初心者ガイドをOllama任意へ更新する

## 受入条件
必須要件がPython API、SQLite、Chrome拡張だけであることが明記される。

## テスト
障害試験、API契約、UI、ビルドを確認する。
