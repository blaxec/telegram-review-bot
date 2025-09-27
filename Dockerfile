FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Делаем entrypoint.sh исполняемым
RUN chmod +x entrypoint.sh

# Устанавливаем netcat для проверки доступности порта БД
RUN apt-get update && apt-get install -y netcat-openbsd && rm -rf /var/lib/apt/lists/*

CMD ["./entrypoint.sh"]