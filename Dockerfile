# https://github.com/sparfenyuk/mcp-proxy

# file: mcp-proxy.Dockerfile

FROM ghcr.io/sparfenyuk/mcp-proxy:v0.5.1

# Install the 'uv' package
RUN python3 -m ensurepip && pip install --no-cache-dir uv

ENV PATH="/usr/local/bin:$PATH" \
    UV_PYTHON_PREFERENCE=only-system

ADD . /mcp-obsidian

RUN (cd /mcp-obsidian && uv sync --frozen)

WORKDIR /mcp-obsidian

ENTRYPOINT [ "./entrypoint.sh" ]
