FROM ghcr.io/astral-sh/uv:0.10.7 AS uv

FROM python:3.14.7-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_CACHE=1 \
    PATH=/app/.venv/bin:$PATH \
    MINI_AEC_API_HOST=0.0.0.0 \
    MINI_AEC_API_PORT=8000 \
    MINI_AEC_IFC_FILE=/app/examples/sample_office.ifc \
    MINI_AEC_IFC_RULES_FILE=/app/data/rules/bfa_2025_accessibility.json \
    MINI_AEC_BUILDING_FILE=/app/data/building.json \
    MINI_AEC_REGULATIONS_FILE=/app/data/regulations.json \
    MINI_AEC_REGULATION_INDEX=/app/data/processed/regulation_chunks.json

WORKDIR /app

COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src

RUN uv sync --locked --no-dev --no-editable

COPY data ./data
COPY examples/sample_office.ifc ./examples/sample_office.ifc

RUN groupadd --system appuser \
    && useradd --system --gid appuser --home-dir /app --no-create-home appuser

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["mini-aec-api"]
