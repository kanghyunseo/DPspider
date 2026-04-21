# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Seoul

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# SQLite DB and materialized credentials go here.
# Mount a Railway Volume at /data to persist conversation history
# and refreshed Google tokens across redeploys.
ENV DB_PATH=/data/assistant.db \
    GOOGLE_TOKEN_PATH=/data/token.json \
    GOOGLE_CREDENTIALS_PATH=/data/credentials.json
RUN mkdir -p /data

CMD ["python", "main.py"]
