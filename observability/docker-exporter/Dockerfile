FROM python:3.12-alpine
WORKDIR /app
COPY exporter.py /app/exporter.py
EXPOSE 9101
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://127.0.0.1:9101/healthz >/dev/null || exit 1
CMD ["python", "/app/exporter.py"]
