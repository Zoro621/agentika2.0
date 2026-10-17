FROM node:24-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY frontend ./frontend
COPY index.html tsconfig.json vite.config.ts ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CB_DATA_DIR=/data CB_DATABASE_URL=sqlite:////data/claimbreaker.db OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml ./
COPY backend ./backend
RUN pip install --no-deps . && useradd --uid 10001 --create-home claimbreaker && mkdir -p /data /app/.claimbreaker && chown claimbreaker:claimbreaker /data /app/.claimbreaker
COPY --from=frontend /build/dist ./dist
COPY alembic.ini ./
COPY migrations ./migrations
USER claimbreaker
EXPOSE 5173
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5173/api/v1/health/ready',timeout=4)"
CMD ["uvicorn","claimbreaker.app:app","--app-dir","/app/backend","--host","0.0.0.0","--port","5173","--workers","1","--proxy-headers"]
