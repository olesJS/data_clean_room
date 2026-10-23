# Data Clean Room

A secure Data Clean Room platform featuring a FastAPI backend, PostgreSQL database, and React frontend.

## 🚀 Quick Start (Свіжий клон запускається однією командою)

### 1. Клонування репозиторію
```bash
git clone https://github.com/olesJS/data_clean_room.git
cd data_clean_room
```

### 2. Запуск однією командою
Всі змінні середовища за замовчуванням уже прописані в `docker-compose.yml`, тому для запуску достатньо однієї команди:

```bash
docker compose up --build -d
```

> **Примітка:** За бажанням налаштування власних змінних можна створити `.env`:
> ```bash
> cp .env.example .env
> ```

---

## 🌐 Доступні сервіси

| Сервіс | Адреса | Опис |
| :--- | :--- | :--- |
| **Frontend** | [http://localhost](http://localhost) | Інтерфейс користувача (React / Vite) |
| **Backend API** | [http://localhost:8000](http://localhost:8000) | REST API (FastAPI) |
| **API Docs (Swagger)** | [http://localhost:8000/docs](http://localhost:8000/docs) | Інтерактивна документація API |
| **Database** | `localhost:5432` | PostgreSQL 15 |

---

## 🛠️ Тестування та перевірка коду (CI / Локально)

### Backend (Python / FastAPI)
Всі тести та перевірки якості коду виконуються автоматично в GitHub Actions на кожен Pull Request / Push.

1. **Запуск лінтера (Ruff):**
   ```bash
   cd backend
   ruff check .
   ```

2. **Запуск тестів (Pytest):**
   ```bash
   cd backend
   pytest
   ```

3. **Запуск тестів всередині Docker-контейнера:**
   ```bash
   docker compose exec backend pytest
   ```

### Frontend (React / Vite)
1. **Лінтер:**
   ```bash
   cd frontend
   npm run lint
   ```
2. **Збірка:**
   ```bash
   cd frontend
   npm run build
   ```

---

## 🔄 CI Pipeline (GitHub Actions)
Налаштовано у файлі [`.github/workflows/ci.yml`](.github/workflows/ci.yml):
- **Backend Lint and Test**: перевірка `ruff` та виконання unit-тестів `pytest`.
- **Frontend Lint and Build**: перевірка `npm run lint` та тестова збірка `npm run build`.
- **Docker Compose Smoke Test**: тестове підняття стеку контейнерів (`backend`, `frontend`, `db`) та перевірка ендпоінтів здоров'я сервісів.