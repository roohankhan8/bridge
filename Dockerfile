FROM python:3.11-slim

LABEL org.opencontainers.image.source="https://github.com/roohankhan8/bridge"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

RUN pip install --no-cache-dir . \
    && useradd --uid 10001 --create-home app \
    && install -d --owner=10001 --group=10001 /app/uploads

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
