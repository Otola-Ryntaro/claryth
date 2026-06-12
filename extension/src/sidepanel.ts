// Side-panel controller: resolve names, require confirmation, then request DB checks.
import type { Candidate, CheckResult, InteractionStatus, ResolutionItem, TargetDrug } from "./types.js";

const API_BASE = "http://127.0.0.1:8765";
const byId = <T extends HTMLElement>(id: string): T => {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing element: ${id}`);
  return element as T;
};

const input = byId<HTMLTextAreaElement>("drug-input");
const targetSelect = byId<HTMLSelectElement>("target-select");
const targetHelp = byId<HTMLParagraphElement>("target-help");
const llmToggle = byId<HTMLInputElement>("llm-toggle");
const checkButton = byId<HTMLButtonElement>("check-button");
const confirmButton = byId<HTMLButtonElement>("confirm-button");
const healthButton = byId<HTMLButtonElement>("health-button");
const statusText = byId<HTMLSpanElement>("status-text");
const datasetMeta = byId<HTMLParagraphElement>("dataset-meta");
const errorBox = byId<HTMLElement>("error-box");
const candidateSection = byId<HTMLElement>("candidate-section");
const candidateList = byId<HTMLElement>("candidate-list");
const candidateCount = byId<HTMLElement>("candidate-count");
const resultSection = byId<HTMLElement>("result-section");
const resultList = byId<HTMLElement>("result-list");
const resultCount = byId<HTMLElement>("result-count");
const resultTarget = byId<HTMLElement>("result-target");
const runtimeRefreshButton = byId<HTMLButtonElement>("runtime-refresh-button");
const startApiButton = byId<HTMLButtonElement>("start-api-button");
const startOllamaButton = byId<HTMLButtonElement>("start-ollama-button");
const warmupButton = byId<HTMLButtonElement>("warmup-button");
const copyInstallButton = byId<HTMLButtonElement>("copy-install-button");
const copyApiButton = byId<HTMLButtonElement>("copy-api-button");
const copyOllamaButton = byId<HTMLButtonElement>("copy-ollama-button");
const apiRuntimeStatus = byId<HTMLElement>("api-runtime-status");
const ollamaRuntimeStatus = byId<HTMLElement>("ollama-runtime-status");
const modelRuntimeStatus = byId<HTMLElement>("model-runtime-status");
const runtimeMessage = byId<HTMLElement>("runtime-message");
const llmControls = byId<HTMLElement>("llm-controls");

let resolutions: ResolutionItem[] = [];
let targets: TargetDrug[] = [];
let projectRoot = "<くらりすフォルダ>";
let apiConnected = false;
let ollamaConnected = false;
const selectedCandidates = new Map<string, Candidate>();

const labels: Record<InteractionStatus, string> = {
  contraindicated: "併用禁忌",
  caution: "併用注意",
  not_listed: "記載なし",
  unresolved: "要確認",
  unsupported: "未収載",
  system_error: "システムエラー",
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      signal: AbortSignal.timeout(25000),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new Error("処理が時間切れになりました。判定APIの状態を再確認してください。");
    }
    throw new Error("ローカルAPIへ接続できませんでした。");
  }
  if (!response.ok) {
    let message = `APIエラー (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function showError(message: string): void {
  errorBox.textContent = message;
  errorBox.classList.remove("hidden");
}

function clearError(): void {
  errorBox.textContent = "";
  errorBox.classList.add("hidden");
}

function setBusy(busy: boolean): void {
  checkButton.disabled = busy;
  confirmButton.disabled = busy;
  checkButton.textContent = busy ? "確認しています..." : "相互作用を確認";
}

function setRuntimeState(
  element: HTMLElement,
  text: string,
  state: "ready" | "warning" | "error" | "pending",
): void {
  element.textContent = text;
  element.className = `runtime-state ${state}`;
}

async function loadProjectConfig(): Promise<void> {
  try {
    const response = await fetch("project-config.json");
    if (response.ok) {
      const config = (await response.json()) as { projectRoot?: string };
      if (config.projectRoot) projectRoot = config.projectRoot;
    }
  } catch {
    // The placeholder remains useful for source-only or non-built previews.
  }
}

function updateTargetDescription(): void {
  const target = targets.find((item) => item.id === targetSelect.value);
  if (!target) return;
  targetHelp.textContent = `${target.group_label} / 順位 ${target.rank} / 代表成分`;
}

async function loadTargets(): Promise<void> {
  try {
    targets = await api<TargetDrug[]>("/v1/targets");
    targetSelect.replaceChildren();
    for (const target of targets) {
      const option = document.createElement("option");
      option.value = target.id;
      option.textContent = `${target.rank}. ${target.label}（${target.group_label}）`;
      option.selected = target.is_default;
      targetSelect.append(option);
    }
    updateTargetDescription();
  } catch {
    targetHelp.textContent = "トップ20 DBを読み込めません。APIとDBを確認してください。";
  }
}

function powershellPath(value: string): string {
  return value.replaceAll("'", "''");
}

async function copyCommand(command: string, label: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(command);
    runtimeMessage.textContent = `${label}をコピーしました。PowerShellへ貼り付けて実行してください。`;
  } catch {
    runtimeMessage.textContent = `コピーできませんでした。コマンド: ${command}`;
  }
}

async function openLauncher(uri: string, service: "api" | "ollama"): Promise<void> {
  runtimeMessage.textContent = "Windowsランチャーの起動確認を許可してください。起動後、自動で再確認します。";
  try {
    if (typeof chrome !== "undefined" && chrome.tabs) {
      await chrome.tabs.create({ url: uri, active: true });
    } else {
      window.location.href = uri;
    }
  } catch {
    runtimeMessage.textContent = "ランチャーを開けませんでした。初回設定の登録コマンドを実行してください。";
    return;
  }
  for (let attempt = 0; attempt < 15; attempt += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 1000));
    await refreshHealth();
    if (service === "api" && apiConnected) break;
    if (service === "ollama" && ollamaConnected) break;
  }
}

async function refreshHealth(): Promise<void> {
  try {
    const health = await api<{
      database: string;
      dataset_version: string | null;
      review_status: string | null;
      top20_database: string;
      top20_review_status: string | null;
    }>("/health");
    apiConnected = health.database === "ok";
    healthButton.classList.remove("offline");
    healthButton.classList.add("online");
    statusText.textContent = "DB接続済み";
    setRuntimeState(apiRuntimeStatus, apiConnected ? "起動済み" : "DBエラー", apiConnected ? "ready" : "error");
    datasetMeta.textContent = `シード ${health.dataset_version ?? "不明"} / Top20 ${health.top20_database}・${health.top20_review_status ?? "状態不明"}`;
    if (llmToggle.checked) await refreshLlmStatus();
    else runtimeMessage.textContent = "AI補助なしで一般名・販売名・誤字候補を検索できます。";
  } catch {
    apiConnected = false;
    ollamaConnected = false;
    healthButton.classList.remove("online");
    healthButton.classList.add("offline");
    statusText.textContent = "API未接続";
    setRuntimeState(apiRuntimeStatus, "停止中", "error");
    warmupButton.disabled = true;
    runtimeMessage.textContent = "「判定APIを起動」を押してください。初回だけランチャー登録が必要です。";
    datasetMeta.textContent = "ローカルAPIを起動してください。";
  }
}

async function refreshLlmStatus(): Promise<void> {
  if (!apiConnected) {
    ollamaConnected = false;
    setRuntimeState(ollamaRuntimeStatus, "API起動後に確認", "pending");
    setRuntimeState(modelRuntimeStatus, "API起動後に確認", "pending");
    warmupButton.disabled = true;
    return;
  }
  try {
    const status = await api<{
      model: string;
      server: boolean;
      model_available: boolean;
      model_loaded: boolean;
    }>("/v1/llm/status");
    ollamaConnected = status.server;
    setRuntimeState(ollamaRuntimeStatus, status.server ? "起動済み" : "停止中", status.server ? "ready" : "warning");
    if (!status.server) setRuntimeState(modelRuntimeStatus, "確認不可", "pending");
    else if (!status.model_available) setRuntimeState(modelRuntimeStatus, "未導入", "warning");
    else if (status.model_loaded) setRuntimeState(modelRuntimeStatus, "読込済み", "ready");
    else setRuntimeState(modelRuntimeStatus, "待機中", "warning");
    warmupButton.disabled = !status.server || !status.model_available;
    runtimeMessage.textContent = !status.server
      ? "Ollamaは停止中です。AI補助なしでも判定できます。"
      : status.model_available
        ? `${status.model}は${status.model_loaded ? "読込済み" : "必要時に読み込まれます"}。`
        : `${status.model}は未導入です。AI補助なしでも判定できます。`;
  } catch {
    ollamaConnected = false;
    setRuntimeState(ollamaRuntimeStatus, "確認失敗", "warning");
    setRuntimeState(modelRuntimeStatus, "確認失敗", "pending");
    warmupButton.disabled = true;
    runtimeMessage.textContent = "AI補助の状態を確認できません。DB判定はそのまま利用できます。";
  }
}

async function warmupModel(): Promise<void> {
  if (!apiConnected) {
    await openLauncher("clarith://start-api", "api");
    if (!apiConnected) return;
  }
  warmupButton.disabled = true;
  warmupButton.textContent = "モデルを読み込み中...";
  runtimeMessage.textContent = "初回は数十秒かかることがあります。相互作用判定はDBから変更されません。";
  try {
    await api<{ status: string; model: string }>("/v1/ollama/warmup", { method: "POST" });
    await refreshLlmStatus();
  } catch (error) {
    showError(error instanceof Error ? error.message : "LLMモデルを読み込めませんでした。");
  } finally {
    warmupButton.textContent = "LLMをメモリへ読み込む";
    warmupButton.disabled = !ollamaConnected;
  }
}

function optionLabel(candidate: Candidate): string {
  const generic = candidate.generic_name ? ` / ${candidate.generic_name}` : "";
  return `${candidate.display_name}${generic} (${Math.round(candidate.score)}%)`;
}

function renderCandidates(): void {
  candidateList.replaceChildren();
  selectedCandidates.clear();
  const pending = resolutions.filter((item) => item.status === "unresolved");
  candidateCount.textContent = `${pending.length}件`;
  if (!pending.length) {
    candidateSection.classList.add("hidden");
    return;
  }
  for (const item of pending) {
    const row = document.createElement("div");
    row.className = "candidate-row";
    const label = document.createElement("label");
    label.textContent = `「${item.input_name}」の候補`;
    const select = document.createElement("select");
    select.setAttribute("aria-label", `${item.input_name}の候補`);
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "候補を選択してください";
    select.append(placeholder);
    for (const candidate of item.candidates) {
      const option = document.createElement("option");
      option.value = candidate.drug_id;
      option.textContent = optionLabel(candidate);
      select.append(option);
    }
    select.addEventListener("change", () => {
      const candidate = item.candidates.find((value) => value.drug_id === select.value);
      if (candidate) selectedCandidates.set(item.input_name, candidate);
      else selectedCandidates.delete(item.input_name);
      confirmButton.disabled = selectedCandidates.size !== pending.length;
    });
    const message = document.createElement("p");
    message.textContent = item.message ?? "候補を確認してください。";
    row.append(label, select, message);
    candidateList.append(row);
  }
  confirmButton.disabled = true;
  candidateSection.classList.remove("hidden");
}

function addDefinition(list: HTMLElement, term: string, value: string): void {
  const group = document.createElement("div");
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = term;
  dd.textContent = value;
  group.append(dt, dd);
  list.append(group);
}

function createResultCard(result: CheckResult): HTMLElement {
  const card = document.createElement("article");
  card.className = `result-card ${result.status}`;
  const main = document.createElement("div");
  main.className = "result-main";
  const top = document.createElement("div");
  top.className = "result-top";
  const names = document.createElement("div");
  const name = document.createElement("h3");
  name.className = "result-name";
  name.textContent = result.display_name;
  const generic = document.createElement("p");
  generic.className = "result-generic";
  generic.textContent = result.ingredients.join(" / ");
  names.append(name, generic);
  const severity = document.createElement("span");
  severity.className = `severity ${result.status}`;
  severity.textContent = labels[result.status];
  top.append(names, severity);
  const effect = document.createElement("p");
  effect.className = "effect";
  effect.textContent = result.effect;
  const action = document.createElement("p");
  action.className = "action";
  action.textContent = result.action;
  main.append(top, effect, action);
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "根拠と詳細を表示";
  const detailGrid = document.createElement("dl");
  detailGrid.className = "detail-grid";
  addDefinition(detailGrid, "機序", result.mechanism);
  addDefinition(detailGrid, "入力", result.input_name);
  addDefinition(detailGrid, "データ更新日", result.dataset_updated_at);
  if (result.source_section) addDefinition(detailGrid, "電子添文の項目", result.source_section);
  if (result.source_revision) addDefinition(detailGrid, "出典改訂", result.source_revision);
  if (result.evidence_url) {
    const group = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    const link = document.createElement("a");
    dt.textContent = "該当箇所";
    link.className = "source-link evidence-link";
    link.href = result.evidence_url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = "該当相互作用をすぐ表示";
    dd.append(link);
    group.append(dt, dd);
    detailGrid.append(group);
  }
  if (result.source_url) {
    const group = document.createElement("div");
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    const link = document.createElement("a");
    dt.textContent = "原資料";
    link.className = "source-link";
    link.href = result.source_url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = result.source_url.includes("ResultDataSetPDF")
      ? "PMDA電子添文PDFを開く"
      : "PMDA情報検索を開く";
    dd.append(link);
    group.append(dt, dd);
    detailGrid.append(group);
  }
  if (result.ingredient_results.length > 1) {
    const ingredientText = result.ingredient_results
      .map((item) => `${item.generic_name}: ${labels[item.status]}`)
      .join(" / ");
    addDefinition(detailGrid, "配合成分別", ingredientText);
  }
  details.append(summary, detailGrid);
  card.append(main, details);
  return card;
}

function createUnsupportedCard(item: ResolutionItem): HTMLElement {
  const selectedTarget = targets.find((target) => target.id === targetSelect.value);
  return createResultCard({
    input_name: item.input_name,
    drug_id: "unsupported",
    display_name: item.input_name,
    generic_name: null,
    category: "ingredient",
    ingredients: ["薬剤を特定できませんでした"],
    status: "unsupported",
    effect: item.message ?? "現在の薬剤マスターでは特定できませんでした。",
    mechanism: "未特定の薬剤について相互作用判定は行っていません。",
    action: "名称を確認するか、最新の電子添文で個別に確認してください。",
    evidence_url: null,
    source_url: null,
    source_section: null,
    source_revision: null,
    dataset_updated_at: "-",
    ingredient_results: [],
    target_id: targetSelect.value,
    target_name: selectedTarget?.label ?? "選択薬",
  });
}

async function runCheck(): Promise<void> {
  const items = resolutions.flatMap((item) => {
    const candidate = item.selected ?? selectedCandidates.get(item.input_name);
    return candidate ? [{ input_name: item.input_name, drug_id: candidate.drug_id }] : [];
  });
  const unsupported = resolutions.filter((item) => item.status === "unsupported");
  if (!items.length && !unsupported.length) return;
  setBusy(true);
  try {
    const response = items.length
      ? await api<{ results: CheckResult[]; disclaimer: string }>("/v1/check", {
          method: "POST",
          body: JSON.stringify({ items, target_id: targetSelect.value }),
        })
      : { results: [], disclaimer: "" };
    resultList.replaceChildren();
    for (const result of response.results) resultList.append(createResultCard(result));
    for (const item of unsupported) resultList.append(createUnsupportedCard(item));
    resultCount.textContent = `${response.results.length + unsupported.length}件`;
    const selectedTarget = targets.find((item) => item.id === targetSelect.value);
    resultTarget.textContent = selectedTarget ? `基準薬：${selectedTarget.label}` : "";
    resultSection.classList.remove("hidden");
    candidateSection.classList.add("hidden");
  } catch (error) {
    showError(error instanceof Error ? error.message : "判定処理に失敗しました。");
  } finally {
    setBusy(false);
  }
}

async function resolveAndCheck(): Promise<void> {
  clearError();
  resultSection.classList.add("hidden");
  candidateSection.classList.add("hidden");
  if (!input.value.trim()) {
    showError("薬剤名を1件以上入力してください。");
    return;
  }
  setBusy(true);
  try {
    const response = await api<{ items: ResolutionItem[] }>("/v1/resolve", {
      method: "POST",
      body: JSON.stringify({ text: input.value, use_llm: llmToggle.checked }),
    });
    resolutions = response.items;
    renderCandidates();
    if (!resolutions.some((item) => item.status === "unresolved")) await runCheck();
  } catch (error) {
    showError(error instanceof Error ? error.message : "薬剤名の確認に失敗しました。");
  } finally {
    setBusy(false);
  }
}

for (const chip of document.querySelectorAll<HTMLButtonElement>(".example-chip")) {
  chip.addEventListener("click", () => {
    const value = chip.dataset.value;
    if (!value) return;
    input.value = input.value.trim() ? `${input.value.trim()}\n${value}` : value;
    input.focus();
  });
}

checkButton.addEventListener("click", () => void resolveAndCheck());
confirmButton.addEventListener("click", () => void runCheck());
healthButton.addEventListener("click", () => void refreshHealth());
runtimeRefreshButton.addEventListener("click", () => void refreshHealth());
startApiButton.addEventListener("click", () => void openLauncher("clarith://start-api", "api"));
startOllamaButton.addEventListener("click", () => void openLauncher("clarith://start-ollama", "ollama"));
warmupButton.addEventListener("click", () => void warmupModel());
copyInstallButton.addEventListener("click", () => {
  const script = `${projectRoot}\\scripts\\install_windows_launcher.ps1`;
  void copyCommand(
    `powershell -NoProfile -ExecutionPolicy Bypass -File '${powershellPath(script)}'`,
    "ランチャー登録コマンド",
  );
});
copyApiButton.addEventListener("click", () => {
  void copyCommand(
    `Set-Location -LiteralPath '${powershellPath(projectRoot)}'; python -m backend.app`,
    "API起動コマンド",
  );
});
copyOllamaButton.addEventListener("click", () => {
  void copyCommand("ollama serve", "Ollama起動コマンド");
});
input.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") void resolveAndCheck();
});
targetSelect.addEventListener("change", () => {
  updateTargetDescription();
  resultSection.classList.add("hidden");
  candidateSection.classList.add("hidden");
});
llmToggle.addEventListener("change", () => {
  llmControls.classList.toggle("hidden", !llmToggle.checked);
  if (llmToggle.checked) void refreshLlmStatus();
  else runtimeMessage.textContent = "AI補助なしで一般名・販売名・誤字候補を検索できます。";
});

void loadProjectConfig();
void refreshHealth().then(() => loadTargets());
