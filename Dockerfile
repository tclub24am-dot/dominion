# Базовый образ
FROM python:3.12-slim

# Установка рабочей директории
WORKDIR /app

# Копирование файла зависимостей и установка
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование всего проекта
COPY . .

# Создание скрипта инициализации
RUN echo '#!/bin/bash\n\
echo "Ожидание готовности базы данных..."\n\
sleep 5\n\
echo "Создание таблиц в базе данных..."\n\
python -m app.create_db\n\
echo "Создание пользователя master..."\n\
python -m app.create_master_user\n\
echo "Запуск приложения..."\n\
exec uvicorn main:app --host 0.0.0.0 --port 8001\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Команда для запуска приложения через скрипт инициализации
CMD ["/app/entrypoint.sh"]
