# 006 ローカルAPIとOllama

## 目的
DB判定と補助LLMをlocalhost APIとして提供する。

## 対象外
LLMによる相互作用の新規推論。

## 依存
003、005。

## タスク
- [x] health、dataset、resolve、check APIを実装する
- [x] Ollama構造化出力を検証する
- [x] Ollama候補を既存drug_idだけに制限する
- [x] Ollama停止時のフォールバックを実装する
- [x] loopbackバインドとOrigin制限を設定する
- [x] Ollamaの停止・モデル待機・モデル読込済みを区別する
- [x] モデル事前読込APIを実装する

## 受入条件
Ollamaが停止しても完全一致とDB判定が成功する。

## テスト
API契約、Ollama障害、未知drug_id、Origin拒否を確認する。
