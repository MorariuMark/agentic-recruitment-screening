# ==============================================================================
# Stage 1: Build Next.js 16 Production Frontend
# ==============================================================================
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend-next

# Install dependencies with clean install
COPY frontend-next/package*.json ./
RUN npm ci

# Copy frontend source and build Next.js optimized production bundle
COPY frontend-next/ ./
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production
ENV BACKEND_API_URL=http://127.0.0.1:8000
RUN npm run build

# ==============================================================================
# Stage 2: Runtime Engine (FastAPI + Next.js Server)
# ==============================================================================
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860 \
    BACKEND_API_URL=http://127.0.0.1:8000

WORKDIR /app

# Install system utilities and Node.js 20 runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install lightweight CPU-only PyTorch (avoids massive CUDA download)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install Python backend dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code, seeds, and supervisor script
COPY backend/ ./backend/
COPY data/ ./data/
COPY start_container.py ./start_container.py

# Copy pre-built frontend from Stage 1
COPY --from=frontend-builder /app/frontend-next ./frontend-next

# Create non-root user (UID 1000) for standard cloud / Hugging Face Spaces compliance
RUN useradd -m -u 1000 user \
    && chown -R user:user /app \
    && chmod -R 775 /app/data

USER user

EXPOSE 7860

CMD ["python", "start_container.py"]
