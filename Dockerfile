# Continuum — one image for both the HTTP API and the remote MCP server.
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir -e ".[all]"   # api + mcp + httpx (llm)

ENV CONTINUUM_HOME=/data CONTINUUM_BACKEND=local
VOLUME ["/data"]
EXPOSE 8770

HEALTHCHECK --interval=30s --timeout=3s \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://127.0.0.1:8770/health').status_code==200 else 1)"

CMD ["continuum", "serve", "--host", "0.0.0.0", "--port", "8770"]
