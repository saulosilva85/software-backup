FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BACKUPHUB_DATA_DIR=/data \
    BACKUPHUB_PORT=8080

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backuphub ./backuphub

RUN useradd --system --uid 10001 backuphub && mkdir -p /data && chown backuphub /data
USER backuphub
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')"

# 1 worker: o agendador e a fila de backups rodam dentro do processo.
CMD ["gunicorn", "--workers", "1", "--threads", "32", "--timeout", "0", "--bind", "0.0.0.0:8080", "backuphub.wsgi:app"]
