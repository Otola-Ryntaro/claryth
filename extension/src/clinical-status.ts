export type ClinicalUiState = "ready" | "review" | "integrity" | "offline" | "pending";

export interface ClinicalStatusContent {
  state: ClinicalUiState;
  label: string;
  title: string;
  message: string;
}

export function integrityMessage(reason: string): string {
  if (reason.includes("expired")) {
    return "署名manifestの有効期限が切れています。正規の最新版データを再導入してください。";
  }
  if (reason.includes("signature")) {
    return "データの電子署名を確認できません。正規の配布物を再導入してください。";
  }
  if (reason.includes("hash mismatch") || reason.includes("integrity_check")) {
    return "データの破損または変更を検出しました。現在のDBは使用しないでください。";
  }
  if (reason.includes("missing") || reason.includes("unreadable")) {
    return "判定に必要な署名ファイルまたはDBを読み込めません。配布物を再導入してください。";
  }
  return "DBの完全性を確認できません。現在のDBは使用せず、管理者へ連絡してください。";
}

export function clinicalStatusContent(
  connected: boolean,
  clinicalReady: boolean,
  integrityOk: boolean,
  integrityReason = "",
): ClinicalStatusContent {
  if (!connected) {
    return {
      state: "offline",
      label: "判定利用不可",
      title: "判定APIへ接続できません",
      message: "判定APIを起動して再確認してください。接続が戻るまで相互作用判定は利用できません。",
    };
  }
  if (clinicalReady && integrityOk) {
    return {
      state: "ready",
      label: "判定利用可",
      title: "承認済みデータを確認しました",
      message: "医学レビューとDB完全性検証が完了しています。結果と最新の電子添文を併せて確認してください。",
    };
  }
  if (!integrityOk) {
    return {
      state: "integrity",
      label: "判定利用不可",
      title: "DB完全性検証に失敗しました",
      message: integrityMessage(integrityReason),
    };
  }
  return {
    state: "review",
    label: "臨床利用禁止",
    title: "医学レビューが完了していません",
    message: "薬剤名検索と状態確認だけ利用できます。相互作用判定には使用しないでください。",
  };
}

export function reviewStatusLabel(status: string | null): string {
  if (status === "clinically_reviewed") return "医学レビュー済み";
  if (status === "pmda_extracted_review_required") return "PMDA抽出後・医学レビュー未完了";
  if (status === "prototype_manual_review_required") return "試作データ・医学レビュー未完了";
  return status ? "医学レビュー状態を確認できません" : "レビュー情報がありません";
}
