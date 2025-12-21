FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps: ffmpeg for merging/transcoding, plus certs/tzdata.
RUN apt-get update \
    ; apt-get install -y --no-install-recommends ffmpeg ca-certificates tzdata \
    ; rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

CMD ["python", "main.py"]

