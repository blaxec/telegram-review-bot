#!/bin/sh

# Ждем, пока база данных будет готова
# (Это необязательно, но является хорошей практикой)
echo "Waiting for postgres..."
while ! nc -z postgres_db 5432; do
  sleep 0.1
done
echo "PostgreSQL started"

# Применяем миграции базы данных
echo "Applying database migrations..."
alembic upgrade head

# Запускаем основное приложение бота
echo "Starting bot..."
exec python main.py