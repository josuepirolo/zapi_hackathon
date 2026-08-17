"""Client MCP Z-API de produto.

Promovido de `scripts/mcp_oauth_experiment.py` (experimento de Fase 0,
validado ao vivo: OAuth 2.1 com Dynamic Client Registration + PKCE,
`tools/list` com as 9 tools reais, `send-text` executado com sucesso).
O fluxo OAuth em si (autorizacao, PKCE, persistencia/renovacao de token)
nao muda — so vira modulo importavel em vez de CLI.

Tokens ja emitidos na Fase 0 ficam em `.mcp_auth/` (fora do git) e sao
reutilizados via refresh_token; se expirarem/forem revogados, a primeira
chamada abre o navegador para nova autorizacao manual (mesmo
comportamento do experimento original).

Unico ponto de import do SDK MCP (`mcp[cli]`) do projeto - ver
`.sdds/harness/consentimento-grupo.harness.md`, secao 8 (Centralizacao).
"""

from __future__ import annotations

import json
import logging
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable
from urllib.parse import parse_qs, urlparse

import anyio
from mcp import ClientSession
from mcp.client.auth.oauth2 import OAuthClientProvider
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

logger = logging.getLogger("delega.mcp_client")

MCP_SERVER_URL = "https://mcp.z-api.io/mcp"

# Falhas de rede transitorias (DNS instavel na VM, observado repetidas
# vezes ao vivo - "Name or service not known") nao podem derrubar o
# fluxo de consentimento. 3 tentativas com backoff curto antes de desistir
# de verdade (o chamador ja trata a excecao final sem quebrar o webhook).
MAX_ATTEMPTS = 3
RETRY_BASE_DELAY_SECONDS = 1.0
CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 8765
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}/callback"

AUTH_DIR = Path(__file__).resolve().parent.parent / ".mcp_auth"
TOKENS_FILE = AUTH_DIR / "zapi_tokens.json"
CLIENT_FILE = AUTH_DIR / "zapi_client.json"


class FileTokenStorage:
    """Persistencia simples em arquivo local (fora do git). Protocol: TokenStorage."""

    async def get_tokens(self) -> OAuthToken | None:
        if not TOKENS_FILE.exists():
            return None
        return OAuthToken.model_validate_json(TOKENS_FILE.read_text(encoding="utf-8"))

    async def set_tokens(self, tokens: OAuthToken) -> None:
        AUTH_DIR.mkdir(exist_ok=True)
        TOKENS_FILE.write_text(tokens.model_dump_json(), encoding="utf-8")

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        if not CLIENT_FILE.exists():
            return None
        return OAuthClientInformationFull.model_validate_json(CLIENT_FILE.read_text(encoding="utf-8"))

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        AUTH_DIR.mkdir(exist_ok=True)
        CLIENT_FILE.write_text(client_info.model_dump_json(), encoding="utf-8")


@dataclass
class _CallbackResult:
    code: str | None = None
    state: str | None = None
    iss: str | None = None
    error: str | None = None


def _run_callback_server(result: _CallbackResult, got_request: threading.Event) -> None:
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # silencia log padrao
            pass

        def do_GET(self) -> None:  # noqa: N802 (assinatura exigida pela stdlib)
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            result.code = qs.get("code", [None])[0]
            result.state = qs.get("state", [None])[0]
            result.iss = qs.get("iss", [None])[0]
            result.error = qs.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<html><body><h3>DELEGA - autorizacao concluida.</h3>"
                "<p>Pode fechar esta aba e voltar ao terminal.</p></body></html>".encode("utf-8")
            )
            got_request.set()

    httpd = HTTPServer((CALLBACK_HOST, CALLBACK_PORT), Handler)
    httpd.timeout = 300
    httpd.handle_request()
    httpd.server_close()


async def _redirect_handler(authorization_url: str) -> None:
    webbrowser.open(authorization_url)


async def _callback_handler() -> AuthorizationCodeResult:
    result = _CallbackResult()
    got_request = threading.Event()
    server_thread = threading.Thread(target=_run_callback_server, args=(result, got_request), daemon=True)
    server_thread.start()
    await anyio.to_thread.run_sync(got_request.wait, 300)
    server_thread.join(timeout=5)
    if result.error:
        raise RuntimeError(f"Autorizacao OAuth falhou: {result.error}")
    if not result.code:
        raise RuntimeError("Callback OAuth nao recebeu 'code' (timeout ou cancelamento).")
    return AuthorizationCodeResult(code=result.code, state=result.state, iss=result.iss)


def _build_oauth_provider() -> OAuthClientProvider:
    client_metadata = OAuthClientMetadata(
        client_name="DELEGA - consentimento-grupo",
        redirect_uris=[REDIRECT_URI],  # type: ignore[list-item]
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        token_endpoint_auth_method="none",
    )
    return OAuthClientProvider(
        server_url=MCP_SERVER_URL,
        client_metadata=client_metadata,
        storage=FileTokenStorage(),
        redirect_handler=_redirect_handler,
        callback_handler=_callback_handler,
    )


@asynccontextmanager
async def mcp_session() -> AsyncIterator[ClientSession]:
    """Abre uma sessao MCP autenticada (OAuth via token persistido/renovado)."""
    oauth_provider = _build_oauth_provider()
    async with create_mcp_http_client(auth=oauth_provider) as http_client:
        async with streamable_http_client(MCP_SERVER_URL, http_client=http_client) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                yield session


async def _with_retries(operation_name: str, run: Callable[[ClientSession], Awaitable[Any]]) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            async with mcp_session() as session:
                return await run(session)
        except Exception as exc:  # falha de rede/DNS transitoria, ver MAX_ATTEMPTS
            last_exc = exc
            if attempt < MAX_ATTEMPTS:
                delay = RETRY_BASE_DELAY_SECONDS * attempt
                logger.warning(
                    "MCP %s falhou (tentativa %d/%d): %s - retry em %.1fs",
                    operation_name,
                    attempt,
                    MAX_ATTEMPTS,
                    exc,
                    delay,
                )
                await anyio.sleep(delay)
    assert last_exc is not None
    raise last_exc


async def list_tools() -> list[dict[str, Any]]:
    async def _run(session: ClientSession) -> list[dict[str, Any]]:
        result = await session.list_tools()
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in result.tools]

    return await _with_retries("list_tools", _run)


_TOOLS_CACHE_TTL_SECONDS = 300.0
_tools_cache: list[dict[str, Any]] | None = None
_tools_cache_at: float = 0.0


async def list_tools_cached(ttl_seconds: float = _TOOLS_CACHE_TTL_SECONDS) -> list[dict[str, Any]]:
    """`tools/list` real, com cache curto em memoria de processo.

    Descoberta de tools genuinamente ao vivo (nao um schema hardcoded no
    codigo do produto) - so evita bater no MCP a cada mensagem do chat, ja
    que a lista de tools raramente muda dentro de uma mesma execucao do
    servidor. `ttl_seconds=0` forca ignorar o cache."""
    global _tools_cache, _tools_cache_at
    now = time.monotonic()
    if _tools_cache is not None and (now - _tools_cache_at) < ttl_seconds:
        return _tools_cache
    tools = await list_tools()
    _tools_cache = tools
    _tools_cache_at = now
    return tools


# As 9 tools confirmadas ao vivo (ver docs/zapi-mcp-capabilities.md) -
# revalidar via list_tools() se a Z-API anunciar novas tools.
KNOWN_TOOLS: tuple[str, ...] = (
    "send-text",
    "send-image",
    "send-video",
    "group-create",
    "group-metadata",
    "group-add-participant",
    "group-remove-participant",
    "group-add-admin",
    "group-remove-admin",
)

# Em memoria de processo, so pra alimentar o checklist visual do painel
# (GET /tools-usage) - nao precisa persistir, reinicia com o container.
_used_tools: set[str] = set()


def get_tool_usage() -> dict[str, bool]:
    return {name: name in _used_tools for name in KNOWN_TOOLS}


async def call_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    async def _run(session: ClientSession) -> Any:
        result = await session.call_tool(tool_name, arguments=arguments)
        return result.model_dump()

    result = await _with_retries(f"call_tool({tool_name})", _run)
    _used_tools.add(tool_name)
    return result


def parse_tool_payload(mcp_result: dict[str, Any]) -> dict[str, Any] | None:
    """O retorno real de `tools/call` (confirmado ao vivo) traz o payload
    de negocio como uma STRING JSON dentro de `content[0]['text']`, nao
    como chaves soltas no dict de resultado - ex.:
    `{"content": [{"type": "text", "text": "{\\"success\\": false, ...}"}]}`.
    Um `is_error: False` no envelope so significa que a chamada MCP em si
    funcionou, nao que a operacao de negocio teve sucesso - sempre checar
    a chave `success` do payload parseado antes de considerar concluido.
    """
    content = mcp_result.get("content") if isinstance(mcp_result, dict) else None
    if not isinstance(content, list):
        return None
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            try:
                parsed = json.loads(block.get("text", ""))
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def tool_call_succeeded(mcp_result: dict[str, Any]) -> bool:
    """True se o payload parseado nao indicar falha explicita
    (`success: false`). Payload nao-parseavel e tratado como falha -
    nunca assumir sucesso sem confirmacao."""
    payload = parse_tool_payload(mcp_result)
    if payload is None:
        return False
    return payload.get("success") is not False


def extract_invitation_link(mcp_result: dict[str, Any]) -> str | None:
    """Link chat.whatsapp.com/... do retorno de `group-metadata` (admin da instancia)."""
    payload = parse_tool_payload(mcp_result)
    if payload is None:
        return None
    link = payload.get("invitationLink")
    if isinstance(link, str) and link.startswith("http"):
        return link
    return None


def extract_group_id(mcp_result: dict[str, Any]) -> str | None:
    """Extrai o groupId do retorno de `group-create` (chaves observadas
    ao vivo variam - `groupId`/`id`/`phone`). `None` se o payload nao
    parsear ou indicar falha de negocio (ver `tool_call_succeeded`)."""
    payload = parse_tool_payload(mcp_result)
    if payload is None or payload.get("success") is False:
        return None
    for key in ("groupId", "id", "phone"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _br_phone_variants(digits: str) -> set[str]:
    """Numero movel brasileiro pode aparecer com ou sem o 9o digito
    (DDI+DDD+9+8digitos = 13 digitos, ou DDI+DDD+8digitos = 12) - mesmo
    numero fisico, formatos diferentes. Achado real 2026-08-16: o
    `owner` do `group-metadata` veio sem o 9 (ex.: 554498887777), enquanto o
    numero digitado/configurado costuma vir com (ex.: 5544998887777) - sem
    tolerar isso, a checagem de "ja e participante" erra pro dono/admin
    do proprio grupo. Gera as duas variantes pra comparar certo."""
    variants = {digits}
    if digits.startswith("55") and len(digits) == 13 and digits[4] == "9":
        variants.add(digits[:4] + digits[5:])  # remove o 9
    elif digits.startswith("55") and len(digits) == 12:
        variants.add(digits[:4] + "9" + digits[4:])  # adiciona o 9
    return variants


def mcp_phone_candidates(phone_digits: str) -> list[str]:
    """Ordem de tentativa para group-create/group-add — alterna 9o digito BR."""
    base = _only_digits(phone_digits)
    if not base:
        return []
    ordered: list[str] = [base]
    for variant in _br_phone_variants(base):
        if variant not in ordered:
            ordered.append(variant)
    return ordered


def mcp_error_message(mcp_result: dict[str, Any]) -> str | None:
    payload = parse_tool_payload(mcp_result)
    if payload is None:
        return None
    message = payload.get("message")
    return str(message) if message else None


def phones_equivalent(a: str, b: str) -> bool:
    """True se dois MSISDNs sao o mesmo numero (tolera 9o digito BR)."""
    da = _only_digits(a)
    db = _only_digits(b)
    if not da or not db:
        return False
    return bool(_br_phone_variants(da) & _br_phone_variants(db))


def _only_digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def find_participant(mcp_result: dict[str, Any], phone_digits: str) -> dict[str, Any] | None:
    """Retorna o registro do participante (com `isAdmin`/`isSuperAdmin`)
    se `phone_digits` estiver na lista `participants` do retorno de
    `group-metadata` (schema real confirmado ao vivo 2026-08-16:
    `{"participants": [{"phone": "...", "lid": "...@lid", "isAdmin":
    bool, "isSuperAdmin": bool}]}`). Tolera a variacao do 9o digito."""
    payload = parse_tool_payload(mcp_result)
    if payload is None:
        return None
    participants = payload.get("participants")
    if not isinstance(participants, list):
        return None
    target = _only_digits(phone_digits)
    if not target:
        return None
    target_variants = _br_phone_variants(target)
    for p in participants:
        if not isinstance(p, dict):
            continue
        candidate = _only_digits(str(p.get("phone", "")))
        if candidate and _br_phone_variants(candidate) & target_variants:
            return p
    return None


def group_has_participant(mcp_result: dict[str, Any], phone_digits: str) -> bool:
    """Checa so a presenca (ver `find_participant` pra pegar isAdmin/etc)."""
    return find_participant(mcp_result, phone_digits) is not None
