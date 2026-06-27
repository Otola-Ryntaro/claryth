"""FastAPI entry point for the localhost interaction-checking service."""

from contextlib import asynccontextmanager
import html
import asyncio

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import APP_ID, PROTOCOL_VERSION, STARTUP_NONCE, TOKEN_HEADER
from .auth import configured_token, token_matches
from .checker import SEVERITY_RANK, check_drug
from .config import ROOT, settings, strict_data_guard_enabled
from .database import connect, ensure_database, metadata
from .integrity import IntegrityResult, verify_release_manifest
from .models import CheckRequest, CheckResponse, ResolveRequest, ResolveResponse, TargetDrug
from .normalize import parse_inputs
from .ollama_client import ollama_status, suggest_drug_ids, warmup_ollama
from .review import is_clinically_reviewed
from .security import RequestGuard, RequestSizeLimitMiddleware
from .resolver import llm_candidate_pool, resolve_one
from . import top20


DISCLAIMER = (
    "本結果は医療判断を代替しません。『記載なし』は相互作用がないことの保証ではありません。"
    "必ず最新の電子添文、患者背景、用量、腎・肝機能を確認してください。"
)

release_integrity = IntegrityResult(False, "release integrity has not been verified")
request_guard = RequestGuard(
    max_concurrent=settings.max_concurrent_requests,
    max_expensive=settings.max_concurrent_expensive_requests,
    rate_limits={"/v1/resolve": 60, "/v1/check": 120, "/v1/ollama/warmup": 5},
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    global release_integrity
    ensure_database()
    release_integrity = verify_release_manifest()
    yield


app = FastAPI(
    title="Clarith Local API",
    version="0.1.0",
    lifespan=lifespan,
    debug=False,
    docs_url=None if settings.product_mode else "/docs",
    redoc_url=None if settings.product_mode else "/redoc",
    openapi_url=None if settings.product_mode else "/openapi.json",
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["127.0.0.1", "localhost", "testserver"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", TOKEN_HEADER],
    allow_credentials=False,
)
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)


@app.middleware("http")
async def restrict_browser_origins(request: Request, call_next):
    origin = request.headers.get("origin")
    allowed = origin is None or origin in settings.allowed_origins
    if not allowed:
        return JSONResponse(status_code=403, content={"detail": "許可されていないOriginです"})
    if request.method != "OPTIONS" and request.url.path not in {"/health", "/pairing/config"}:
        expected = configured_token()
        if expected is None:
            return JSONResponse(
                status_code=503,
                content={"detail": "ローカルAPI認証が未設定です。ランチャーを再登録してください。"},
            )
        provided = request.headers.get(TOKEN_HEADER)
        if provided is None:
            return JSONResponse(status_code=401, content={"detail": "API認証トークンが必要です。"})
        if not token_matches(provided):
            return JSONResponse(status_code=403, content={"detail": "API認証トークンが一致しません。"})
    lease = None
    if request.method != "OPTIONS" and request.url.path.startswith("/v1/"):
        lease, retry_after = request_guard.try_enter(request.url.path)
        if lease is None:
            return JSONResponse(
                status_code=429,
                content={"detail": "リクエストが集中しています。少し待って再試行してください。"},
                headers={"Retry-After": str(retry_after)},
            )
    try:
        return await call_next(request)
    finally:
        if lease is not None:
            request_guard.release(lease)


@app.get("/health")
async def health(request: Request) -> dict[str, object]:
    try:
        with connect() as connection:
            data = metadata(connection)
            connection.execute("SELECT 1").fetchone()
        db_ok = True
    except Exception:
        data = {}
        db_ok = False
    top20_ok = top20.available()
    try:
        top20_data = top20.metadata() if top20_ok else {}
    except Exception:
        top20_data = {}
        top20_ok = False
    clinical_source = "top20" if top20_ok else "seed"
    review_ready = (
        top20.clinically_ready()
        if top20_ok
        else db_ok and is_clinically_reviewed(data.get("review_status"))
    )
    strict_guard = strict_data_guard_enabled()
    clinical_ready = review_ready and release_integrity.ok
    check_ready = db_ok and (
        clinical_ready or (not strict_guard and (top20_ok or request.url.path == "/health"))
    )
    return {
        "app_id": APP_ID,
        "protocol_version": PROTOCOL_VERSION,
        "startup_nonce": STARTUP_NONCE,
        "auth_configured": configured_token() is not None,
        "authenticated": token_matches(request.headers.get(TOKEN_HEADER)),
        "api": "ok",
        "database": "ok" if db_ok else "error",
        "dataset_version": data.get("dataset_version"),
        "review_status": data.get("review_status"),
        "top20_database": "ok" if top20_ok else "unavailable",
        "top20_review_status": top20_data.get("review_status"),
        "clinical_ready": check_ready,
        "strict_data_guard": strict_guard,
        "data_review_ready": review_ready,
        "clinical_source": clinical_source,
        "integrity_ok": release_integrity.ok,
        "integrity_reason": release_integrity.reason,
        "release_manifest_id": release_integrity.manifest_id,
        "release_manifest_expires_at": release_integrity.expires_at,
    }


@app.get("/pairing/config")
def pairing_config() -> dict[str, object]:
    token = configured_token()
    if token is None:
        raise HTTPException(status_code=503, detail="ローカルAPI認証が未設定です。")
    return {
        "app_id": APP_ID,
        "protocol_version": PROTOCOL_VERSION,
        "apiToken": token,
        "projectRoot": str(ROOT),
    }


@app.get("/v1/llm/status")
async def llm_status() -> dict[str, object]:
    status = await ollama_status()
    return {"model": settings.ollama_model, **status}


@app.get("/v1/dataset")
def dataset() -> dict[str, str]:
    with connect() as connection:
        return metadata(connection)


@app.get("/v1/targets", response_model=list[TargetDrug])
def targets() -> list[TargetDrug]:
    values = top20.list_targets()
    if not values:
        raise HTTPException(status_code=503, detail="トップ20 PMDAデータベースがありません。")
    return values


@app.get("/v1/evidence/{interaction_id}", response_class=HTMLResponse)
def evidence_page(
    interaction_id: int,
    target_id: str = Query(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9:_-]+$"),
) -> HTMLResponse:
    try:
        item = top20.evidence(interaction_id, target_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="該当する根拠行がありません。") from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    escaped = {key: html.escape(str(value), quote=True) for key, value in item.items()}
    severity_label = "併用禁忌" if item["severity"] == "contraindicated" else "併用注意"
    severity_class = "danger" if item["severity"] == "contraindicated" else "caution"
    content = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{escaped['pair']} - くらりす</title>
<style>
body{{margin:0;background:#f3f6f4;color:#182322;font-family:"Yu Gothic UI",sans-serif}}
main{{max-width:780px;margin:0 auto;padding:28px 18px 48px}}
.eyebrow{{color:#52706a;font-size:12px;font-weight:800;letter-spacing:.1em}}
h1{{margin:5px 0 8px;color:#123d37;font-size:26px}} .meta{{color:#667873;font-size:13px}}
.badge{{display:inline-block;border-radius:999px;padding:5px 10px;font-size:12px;font-weight:800}}
.danger{{background:#f8dfe0;color:#9c2830}} .caution{{background:#fbead4;color:#9a5b0f}}
section{{margin-top:16px;border:1px solid #dce3e0;border-radius:13px;background:#fff;padding:17px}}
h2{{margin:0 0 7px;color:#52706a;font-size:12px}} p{{margin:0;line-height:1.7;white-space:pre-wrap}}
dl{{display:grid;gap:9px}} dt{{color:#83908d;font-size:11px;font-weight:700}} dd{{margin:2px 0 0;line-height:1.6}}
a{{display:inline-block;margin-top:18px;border-radius:10px;background:#145f53;padding:11px 15px;color:#fff;text-decoration:none;font-weight:700}}
.warning{{margin-top:16px;color:#6c7976;font-size:11px;line-height:1.6}}
</style></head><body><main>
<p class="eyebrow">くらりす / 該当相互作用</p><h1>{escaped['pair']}</h1>
<p class="meta">電子添文 {escaped['section']} / 改訂 {escaped['revision_date']}</p>
<p><span class="badge {severity_class}">{severity_label}</span></p>
<section><h2>薬剤名等</h2><p>{escaped['drug_text']}</p></section>
<section><h2>臨床症状・措置方法</h2><p>{escaped['effect']}</p></section>
<section><h2>機序・危険因子</h2><p>{escaped['mechanism']}</p></section>
<section><dl><div><dt>出典文書</dt><dd>{escaped['document_name']}</dd></div>
<div><dt>電子添文番号</dt><dd>{escaped['package_insert_no']}</dd></div></dl>
<a href="{escaped['pdf_url']}" target="_blank" rel="noreferrer">PMDA電子添文PDFを開く</a></section>
<p class="warning">表示内容はローカルDBへ抽出した該当行です。最終確認はリンク先の最新電子添文で行ってください。</p>
</main></body></html>"""
    return HTMLResponse(content=content)


@app.post("/v1/ollama/warmup")
async def ollama_warmup() -> dict[str, object]:
    ready = await warmup_ollama()
    if not ready:
        raise HTTPException(
            status_code=503,
            detail="Ollamaまたは設定モデルを起動できませんでした。",
        )
    return {"status": "ready", "model": settings.ollama_model}


@app.post("/v1/resolve", response_model=ResolveResponse)
async def resolve(request: ResolveRequest) -> ResolveResponse:
    input_names = parse_inputs(request.text, request.inputs)
    if not input_names:
        raise HTTPException(status_code=422, detail="有効な薬剤名がありません")
    if len(input_names) > 20:
        raise HTTPException(status_code=422, detail="薬剤名は20件以内にしてください")
    with connect() as connection:
        items = [resolve_one(connection, name) for name in input_names]
        if request.use_llm:
            unsupported_items = [item for item in items if item.status == "unsupported"]
            work_items = [
                (item, pool)
                for item in unsupported_items
                if (pool := llm_candidate_pool(connection, item.input_name))
            ]
            suggestions = await asyncio.gather(
                *(
                    suggest_drug_ids(
                        item.input_name,
                        [
                            {"drug_id": candidate.drug_id, "name": candidate.display_name}
                            for candidate in pool
                        ],
                    )
                    for item, pool in work_items
                ),
                return_exceptions=True,
            )
            for (item, pool), suggested_ids in zip(work_items, suggestions, strict=True):
                if isinstance(suggested_ids, BaseException):
                    continue
                candidates_by_id = {candidate.drug_id: candidate for candidate in pool}
                valid_ids = [drug_id for drug_id in suggested_ids if drug_id in candidates_by_id][:3]
                if valid_ids:
                    item.status = "unresolved"
                    item.llm_used = True
                    item.message = "AI候補・要確認。選択するまで相互作用判定は行いません。"
                    item.candidates = [candidates_by_id[drug_id] for drug_id in valid_ids]
    return ResolveResponse(items=items)


@app.post("/v1/check", response_model=CheckResponse)
async def check(request: CheckRequest) -> CheckResponse:
    try:
        with connect() as connection:
            data = metadata(connection)
            if top20.available():
                top20.require_clinically_ready()
                if strict_data_guard_enabled() and not release_integrity.ok:
                    raise HTTPException(
                        status_code=503,
                        detail=f"リリースDBの完全性検証に失敗しました: {release_integrity.reason}",
                    )
                results = [
                    top20.check(connection, item.input_name, item.drug_id, request.target_id)
                    for item in request.items
                ]
            else:
                if request.target_id != "clarithromycin":
                    raise HTTPException(status_code=503, detail="トップ20 PMDAデータベースがありません。")
                if strict_data_guard_enabled() and not is_clinically_reviewed(data.get("review_status")):
                    raise HTTPException(
                        status_code=503,
                        detail="判定データは医学レビュー未完了のため、臨床判定には使用できません。",
                    )
                if strict_data_guard_enabled() and not release_integrity.ok:
                    raise HTTPException(
                        status_code=503,
                        detail=f"リリースDBの完全性検証に失敗しました: {release_integrity.reason}",
                    )
                results = [
                    check_drug(connection, item.input_name, item.drug_id, data["updated_at"])
                    for item in request.items
                ]
    except KeyError as error:
        raise HTTPException(status_code=422, detail=f"不明なdrug_idです: {error.args[0]}") from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    results.sort(key=lambda item: (SEVERITY_RANK[item.status], item.display_name))
    return CheckResponse(results=results, disclaimer=DISCLAIMER)
