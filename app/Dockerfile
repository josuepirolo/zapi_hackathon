FROM python:3.12-slim

WORKDIR /app

COPY app/requirements.txt ./app/requirements.txt
RUN pip install --no-cache-dir -r app/requirements.txt

COPY app/ ./app/

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/data /app/.mcp_auth \
    && chown -R appuser:appuser /app \
    && chmod +x /app/app/entrypoint.sh

# Container inicia como root de proposito (nao troca USER aqui) - ver
# entrypoint.sh: corrige a posse dos bind mounts e so entao baixa
# privilegio pro appuser antes de executar o app.
ENTRYPOINT ["/app/app/entrypoint.sh"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
