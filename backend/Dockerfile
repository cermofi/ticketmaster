FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml
COPY ticketmaster /app/ticketmaster
COPY migrations /app/migrations
COPY tests /app/tests

RUN pip install --no-cache-dir --no-build-isolation -e ".[test]"

EXPOSE 8000

CMD ["sh", "-c", "ticketmaster-cli db migrate && uvicorn ticketmaster.api.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2}"]
