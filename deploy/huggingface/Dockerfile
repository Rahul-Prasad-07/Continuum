# Continuum remote MCP server, for a Hugging Face Docker Space.
# This file, the README, pyproject.toml and the src folder all live at the Space root.
FROM python:3.12-slim

# Hugging Face recommends running as a non root user with uid 1000.
RUN useradd -m -u 1000 user

WORKDIR /app
COPY --chown=user pyproject.toml README.md ./
COPY --chown=user src ./src
RUN pip install --no-cache-dir -e ".[all]"

USER user
# Home is writable on a free Space, so keep memory there. It is ephemeral and resets on rebuild.
ENV HOME=/home/user \
    CONTINUUM_HOME=/home/user/data \
    CONTINUUM_BACKEND=local \
    PATH=/home/user/.local/bin:$PATH
RUN mkdir -p /home/user/data

# Hugging Face routes external HTTPS to app_port (8770, set in the README front matter).
EXPOSE 8770

# Remote MCP server. Change to ["continuum","serve","--host","0.0.0.0","--port","8770"]
# for the plain HTTP API instead.
CMD ["continuum", "mcp", "-t", "streamable-http", "--host", "0.0.0.0", "--port", "8770"]
