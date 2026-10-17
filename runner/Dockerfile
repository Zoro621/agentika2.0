FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 HOME=/tmp CB_ISOLATED_EXECUTION=1
WORKDIR /runner
COPY runner/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock
COPY backend/claimbreaker/sandbox_worker.py ./worker.py
COPY backend/claimbreaker/original_worker.py ./original_worker.py
USER 65534:65534
ENTRYPOINT ["python","-I","/runner/worker.py"]
