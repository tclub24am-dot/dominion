
# План развертывания S-GLOBAL DOMINION в Docker

## 1. Dockerfile

- **Базовый образ**: `python:3.12-slim`
- **Рабочая директория**: `/app`
- **Копирование файлов**:
    - `COPY requirements.txt .`
    - `COPY . .`
- **Установка зависимостей**:
    - `RUN pip install --no-cache-dir -r requirements.txt`
- **Переменные окружения**:
    - `ENV` для всех ключей из `.env`
- **Запуск приложения**:
    - `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]`

## 2. docker-compose.yml

- **Сервисы**:
    - `db` (PostgreSQL):
        - **Образ**: `postgres:15`
        - **Переменные окружения**: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
        - **Volume**: `dominion_data:/var/lib/postgresql/data`
    - `app` (FastAPI):
        - **Build**: `.` (из Dockerfile)
        - **Порты**: `8001:8001`
        - **Зависимости**: `depends_on: - db`
        - **Переменные окружения**: из `.env` файла (`env_file`)
- **Сеть**: `dominion_net`
- **Volume**: `dominion_data`

## 3. Nginx (Proxy)

- Будет добавлен позже для распределения нагрузки и HTTPS.

