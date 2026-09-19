FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN groupadd --gid 10001 papierbib && useradd --uid 10001 --gid 10001 --no-create-home papierbib \
    && mkdir /data && chown 10001:10001 /data
COPY __init__.py config.py storage.py images.py server.py /app/mobile_backend/
COPY web /app/mobile_backend/web
COPY tools/make_icons.py /app/make_icons.py
RUN python /app/make_icons.py /app/mobile_backend/web
EXPOSE 8080
USER 10001:10001
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"]
CMD ["uvicorn", "mobile_backend.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log", "--no-proxy-headers", "--limit-concurrency", "16", "--timeout-keep-alive", "5"]
