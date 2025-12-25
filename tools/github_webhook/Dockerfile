FROM python:3.12-alpine

WORKDIR /app

RUN apk add --no-cache git docker-cli docker-cli-compose

RUN pip install --no-cache-dir fastapi uvicorn

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY ./tools/github_webhook /app/tools/github_webhook

EXPOSE 8091

CMD ["python", "-m", "tools.github_webhook.run_webhook"]
