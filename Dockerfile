FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY youtube_learning_app ./youtube_learning_app
COPY youtube-english-web ./youtube-english-web

EXPOSE 8000

CMD sh -c "uvicorn youtube_learning_app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
