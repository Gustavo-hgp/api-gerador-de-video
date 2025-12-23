FROM python:3.11-slim

# ====== ENV ======
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TMP_DIR=/tmp_videos

# ====== SYSTEM DEPS ======
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
 && rm -rf /var/lib/apt/lists/*

# ====== USER ======
RUN useradd -m appuser

WORKDIR /app

# ====== PYTHON DEPS (ANTI-CACHE) ======
COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir --force-reinstall -r requirements.txt

# ====== APP ======
COPY app ./app

# ====== TMP DIR ======
RUN mkdir -p ${TMP_DIR} && chown -R appuser:appuser ${TMP_DIR}

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
