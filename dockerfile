FROM python:3.11-slim

WORKDIR /app

# dependências de sistema
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# dependências python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# código
COPY . .

# cria pasta temporária
RUN mkdir -p tmp_videos

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "80"]

