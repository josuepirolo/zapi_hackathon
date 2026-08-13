#!/bin/sh
# Roda como root (imagem nao troca USER) so pra corrigir a posse dos
# volumes montados via bind mount - que o Docker cria como root no host
# na primeira execucao, mesmo a imagem tendo feito chown em build time -
# e entao baixa privilegio pro appuser antes de executar o app de verdade.
# Sem isso, "docker compose up" numa VM nova (ou apos apagar ./data) falha
# com "unable to open database file" (SQLite) por falta de permissao.
set -e

mkdir -p /app/data /app/.mcp_auth
chown -R appuser:appuser /app/data /app/.mcp_auth

exec gosu appuser "$@"
