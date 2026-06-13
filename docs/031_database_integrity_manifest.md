# 031 DB完全性・署名manifest検証

## 目的
破損、取り違え、改変、未承認、期限切れのDBを起動時に拒否する。

## 対象外
医学レビューの実施手順とWindows実行ファイル署名。

## 依存
016、029。

## タスク
- [x] DBごとのSHA-256、スキーマ版、データ日、レビュー状態をmanifestへ記録する
- [x] レビュー者、レビュー日時、承認IDをmanifestへ記録する
- [x] manifestへ電子署名し、公開鍵をアプリへ同梱する
- [x] 起動時に署名、ハッシュ、`PRAGMA integrity_check`、スキーマ版を検証する
- [x] 検証失敗時はhealthへ理由を返し、判定を停止する
- [x] 改変、欠落、古い版、署名不正のテストを追加する

## 受入条件
署名済みmanifestと一致する承認済みDBだけが臨床判定に使われる。

## テスト
DBを1バイト変更したケースを含め、全不正ケースがfail-closedになることを確認する。

## 実装メモ
- 署名方式はEd25519、署名対象はキー順を固定したcanonical JSONとする。
- 秘密鍵は`.runtime/release_private_key.pem`へ置き、Windowsでは現在ユーザーだけのACLへ制限する。Gitおよび配布物へ含めない。
- 公開鍵は`backend/app/release_public_key.pem`へ同梱する。
- 生成物は`backend/data/release_manifest.json`と`backend/data/release_manifest.sig`で、DBと同じリリース成果物へ含める。
- 医学レビュー済みを示すDBは、レビュー者、レビュー日時、承認IDがmanifestにない限り検証を通さない。
