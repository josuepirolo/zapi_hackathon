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

import threading
import webbrowser
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import parse_qs, urlparse

import anyio
from mcp import ClientSession
from mcp.client.auth.oauth2 import OAuthClientProvider
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from mcp.shared.auth import AuthorizationCodeResult, OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

MCP_SERVER_URL = "https://mcp.z-api.io/mcp"
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


async def list_tools() -> list[dict[str, Any]]:
    async with mcp_session() as session:
        result = await session.list_tools()
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in result.tools]


async def call_tool(tool_name: str, arguments: dict[str, Any]) -> Any:
    async with mcp_session() as session:
        result = await session.call_tool(tool_name, arguments=arguments)
        return result.model_dump()
