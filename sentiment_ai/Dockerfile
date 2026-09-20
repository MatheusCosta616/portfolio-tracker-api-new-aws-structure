FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libssl-dev \
    libffi-dev \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
COPY sentiment_ai/requirements.txt /app/sentiment_ai/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /app/requirements.txt \
    && pip install -r /app/sentiment_ai/requirements.txt

COPY . /app/

CMD ["celery", "-A", "portifolio_tracker_api", "worker", "--loglevel=info", "-Q", "sentiment_analysis", "--concurrency=1", "--prefetch-multiplier=1"]
