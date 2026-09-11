FROM python:3.13.7-slim-bookworm
WORKDIR /app
RUN pip install --no-cache-dir uv==0.10.11
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/backend apps/backend
COPY curricula curricula
COPY alembic.ini ./
COPY migrations migrations
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/apps/backend PYTHONUNBUFFERED=1
RUN useradd --create-home --uid 10001 tiza && mkdir -p /app/data/materials && chown -R tiza:tiza /app/data
USER tiza
EXPOSE 8000
CMD ["uvicorn", "tiza.main:app", "--host", "0.0.0.0", "--port", "8000"]
