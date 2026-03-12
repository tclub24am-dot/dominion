# ============================================================
# S-GLOBAL DOMINION — Dockerfile
# Протокол: VERSHINA v200.14
# ============================================================

# Базовый образ
FROM python:3.12-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Копирование файла зависимостей и установка
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование entrypoint скрипта
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Копирование всего проекта
COPY . .

# Создание директории для хранилища
RUN mkdir -p /root/dominion/storage/uploads

# Открываем порт
EXPOSE 8001

# Команда для запуска приложения через скрипт инициализации
CMD ["/app/entrypoint.sh"]
