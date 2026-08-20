FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# תיקיית data/ נשמרת כ-volume — לא נמחקת בעדכון
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1
ENV ACCESS_DB_PATH=/app/data/access.db

CMD ["python", "-m", "bot"]
