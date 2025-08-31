# Lightweight + current Debian
FROM python:3.11-slim-bookworm

# Ensure UTF-8, no bytecode
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (none strictly required, but curl helps debugging)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# If your platform requires an HTTP port, set KEEPALIVE=true at deploy time
ENV PORT=8080
CMD ["python", "app.py"]
