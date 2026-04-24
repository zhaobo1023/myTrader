# myTrader Model Service - CPU-only inference
FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (CPU-only PyTorch via extra-index-url)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code under model_service/
COPY app/ ./model_service/app/

# Models are mounted from host, not baked into image
VOLUME ["/data/models"]

EXPOSE 8500

CMD ["uvicorn", "model_service.app.main:app", "--host", "0.0.0.0", "--port", "8500"]
