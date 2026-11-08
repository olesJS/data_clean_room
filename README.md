# Data Clean Room

> Безпечна платформа для контрольованого обміну даними, перевірки якості та конфіденційної співпраці з даними.

[![Backend](https://img.shields.io/badge/backend-FastAPI-009688?logo=fastapi&logoColor=white)](backend)
[![Frontend](https://img.shields.io/badge/frontend-React%20%2B%20Vite-646CFF?logo=react&logoColor=white)](frontend)
[![Database](https://img.shields.io/badge/database-PostgreSQL%2015-4169E1?logo=postgresql&logoColor=white)](docker-compose.yml)

Data Clean Room об'єднує backend на FastAPI, frontend на React і PostgreSQL у локальний стек розробки, який запускається однією командою Docker Compose.

## ✨ Можливості

- **Контрольований обмін даними** між постачальниками, споживачами та стюардами даних
- **Керування наборами даних** з метаданими, інформацією про файли та контролем доступу
- **Перевірка якості** за YAML-правилами з деталізацією порушень, пошуком дублікатів і розрахунком Quality Score
- **Privacy workflows** для виявлення PII
- **Реєстр правових підстав** з рольовим доступом і журналом аудиту
- **Інтерактивна документація API** через Swagger UI

## 🧱 Архітектура

```text
┌────────────────────┐       ┌────────────────────┐
│  React + Vite      │──────▶│  FastAPI           │
│  Frontend :80      │       │  Backend :8000     │
└────────────────────┘       └─────────┬──────────┘
                                       │
                              ┌────────▼─────────┐
                              │  PostgreSQL 15    │
                              │  Database :5432   │
                              └───────────────────┘
```

Детальна модель предметної області наведена у [діаграмі класів PlantUML](docs/architecture/class-diagram.puml) та її [рендереній версії](docs/architecture/class-diagram.png).

## 🚀 Швидкий старт

### Передумови

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) з Docker Compose
- Git

### Запуск повного стеку

```bash
git clone https://github.com/olesJS/data_clean_room.git
cd data_clean_room
docker compose up --build -d
```

Конфігурація розробки за замовчуванням визначена у `docker-compose.yml`. Щоб перевизначити її локально, створіть `.env`:

```bash
cp .env.example .env
```

### Зупинка стеку

```bash
docker compose down
```

Щоб також видалити локальний volume PostgreSQL:

```bash
docker compose down -v
```

## 🌐 Сервіси

| Сервіс | URL | Призначення |
| --- | --- | --- |
| Frontend | [http://localhost](http://localhost) | React web application |
| Backend API | [http://localhost:8000](http://localhost:8000) | REST API |
| Swagger UI | [http://localhost:8000/docs](http://localhost:8000/docs) | Інтерактивна документація API |
| PostgreSQL | `localhost:5432` | База даних застосунку |

## 🛠️ Локальна розробка

### Backend (FastAPI)

```bash
cd backend
python -m pip install -r requirements.txt
ruff check .
pytest
```

Запуск API локально:

```bash
uvicorn app.main:app --reload
```

### Frontend (React + Vite)

```bash
cd frontend
npm ci
npm run dev
```

Корисні команди frontend:

```bash
npm run lint
npm run typecheck
npm run build
```

### Запуск тестів у Docker

```bash
docker compose up -d
docker compose exec backend pytest
```

## ✅ Continuous integration

Для кожного push у `main` або `develop`, а також для кожного pull request у ці гілки запускається [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

Pipeline перевіряє:

1. linting backend за допомогою Ruff і тести через Pytest
2. linting frontend і production build
3. збірку Docker Compose та health endpoints backend і frontend

## 📁 Структура репозиторію

```text
.
├── backend/                 # FastAPI-застосунок, моделі, сервіси та тести
├── frontend/                # React + Vite-застосунок
├── data/                    # Приклади наборів даних і YAML-правила якості
├── docs/                    # Архітектурна та Scrum-документація
├── .github/workflows/       # CI pipeline на GitHub Actions
├── docker-compose.yml       # Локальне середовище повного стеку
└── .env.example             # Шаблон змінних середовища
```

## 📚 Документація

- [Діаграма класів архітектури](docs/architecture/class-diagram.puml)
- [Рендерена діаграма архітектури](docs/architecture/class-diagram.png)
- [Sprint-документація](docs/scrum)
- [Змінні середовища](.env.example)

## 📄 Ліцензія

Проєкт розробляється в межах навчального та командного проєкту Data Clean Room.
