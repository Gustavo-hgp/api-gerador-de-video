FROM python:3.11-slim

# Variáveis
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TMP_DIR=/tmp_videos

# Dependências de sistema
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
 && rm -rf /var/lib/apt/lists/*

# Usuário seguro
RUN useradd -m appuser

WORKDIR /app

# Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código
COPY app ./app

# Diretório temporário dos vídeos
RUN mkdir -p ${TMP_DIR} && chown -R appuser:appuser ${TMP_DIR}

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
