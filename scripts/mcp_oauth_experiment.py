"""Experimento Milestone 1-3: conectar ao Server MCP Z-API via OAuth,
listar as tools reais e (opcionalmente) chamar uma tool.

Isto NAO e codigo de produto do DELEGA - e o experimento de validacao
descrito no plano de Fase 0 (docs/zapi-mcp-capabilities.md e o artefato
gerado a partir dele).

Uso:
    python scripts/mcp_oauth_experiment.py list-tools
    python scripts/mcp_oauth_experiment.py call-tool send-text --arg number=5511999999999 --arg message="teste"

O fluxo OAuth (authorization_code + PKCE + Dynamic Client Registration) e
feito pelo SDK oficial `mcp` (mcp.client.auth.OAuthClientProvider). Na
primeira execucao ele abre o navegador para autorizacao manual; tokens sao
persistidos em .mcp_auth/ (fora do git) e reutilizados/renovados nas
proximas execucoes via refresh_token.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import threading
import webbrowser
from dataclasses import dataclass
from pathlib import Path
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
    print("\n[OAuth] Abrindo navegador para autorizacao manual (login Z-API + escolha da instancia):")
    print(f"  {authorization_url}\n")
    webbrowser.open(authorization_url)


async def _callback_handler() -> AuthorizationCodeResult:
    result = _CallbackResult()
    got_request = threading.Event()
    server_thread = threading.Thread(target=_run_callback_server, args=(result, got_request), daemon=True)
    server_thread.start()
    print(f"[OAuth] Aguardando callback em {REDIRECT_URI} (timeout 300s)...")
    await anyio.to_thread.run_sync(got_request.wait, 300)
    server_thread.join(timeout=5)
    if result.error:
        raise RuntimeError(f"Autorizacao OAuth falhou: {result.error}")
    if not result.code:
        raise RuntimeError("Callback OAuth nao recebeu 'code' (timeout ou cancelamento).")
    print("[OAuth] Callback recebido com sucesso.")
    return AuthorizationCodeResult(code=result.code, state=result.state, iss=result.iss)


def build_oauth_provider() -> OAuthClientProvider:
    client_metadata = OAuthClientMetadata(
        client_name="DELEGA (experimento Fase 0)",
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


async def list_tools() -> None:
    oauth_provider = build_oauth_provider()
    async with create_mcp_http_client(auth=oauth_provider) as http_client:
        async with streamable_http_client(MCP_SERVER_URL, http_client=http_client) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                init_result = await session.initialize()
                print(f"\n[MCP] initialize OK - server: {init_result.server_info}")
                tools_result = await session.list_tools()
                print(f"\n[MCP] {len(tools_result.tools)} tool(s) encontradas:\n")
                for tool in tools_result.tools:
                    print(f"- {tool.name}: {tool.description}")
                    print(f"    input_schema: {json.dumps(tool.input_schema, ensure_ascii=False)}")


async def call_tool(tool_name: str, args: dict[str, str]) -> None:
    oauth_provider = build_oauth_provider()
    async with create_mcp_http_client(auth=oauth_provider) as http_client:
        async with streamable_http_client(MCP_SERVER_URL, http_client=http_client) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                print(f"\n[MCP] Chamando tool '{tool_name}' com args {args} ...")
                result = await session.call_tool(tool_name, arguments=args)
                print(f"\n[MCP] Resultado bruto:\n{result.model_dump_json(indent=2)}")


def _parse_kv_args(raw_args: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in raw_args:
        if "=" not in item:
            raise ValueError(f"Argumento invalido (esperado key=value): {item}")
        key, value = item.split("=", 1)
        parsed[key] = value
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-tools", help="Conecta, autentica via OAuth e lista as tools reais do MCP Z-API.")

    call_parser = sub.add_parser("call-tool", help="Chama uma tool especifica do MCP Z-API.")
    call_parser.add_argument("tool_name")
    call_parser.add_argument("--arg", action="append", default=[], help="key=value (repetivel)")

    args = parser.parse_args()

    if args.command == "list-tools":
        asyncio.run(list_tools())
    elif args.command == "call-tool":
        tool_args = _parse_kv_args(args.arg)
        asyncio.run(call_tool(args.tool_name, tool_args))


if __name__ == "__main__":
    main()
