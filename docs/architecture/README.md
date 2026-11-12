# Архітектура Data Clean Room

Цей розділ описує структуру системи, ключові сутності та основні сценарії Sprint 3. Документ є точкою входу для розробників, тестувальників і рев’юерів.

## 1. Огляд системи

Data Clean Room — трирівневий вебзастосунок для безпечного обміну даними між Data Provider і Data Consumer під контролем Data Steward.

| Рівень | Технології | Розташування |
|---|---|---|
| Frontend | React + TypeScript + Vite | `frontend/` |
| Backend | FastAPI + SQLAlchemy | `backend/app/` |
| База даних | PostgreSQL 15 (SQLite в тестах) | Docker volume `postgres_data` |
| Файлове сховище | Локальний volume `uploads_data` | `/app/storage/datasets` у контейнері |

Основні принципи:

- сирий файл ніколи не віддається назовні — exchange працює лише з незмінною clean-версією;
- публікація можлива лише після анонімізації та проходження publication gate;
- доступ до даних надає лише власник набору (DataProvider);
- усі значущі дії пишуться в audit log без PII.

## 2. Діаграми

| Діаграма | Файл | Призначення |
|---|---|---|
| Класи | [`class-diagram.puml`](class-diagram.puml) / [`class-diagram.png`](class-diagram.png) | Сутності БД, зв’язки, поля Sprint 3 |
| Публікація | [`sequence-publish.puml`](sequence-publish.puml) / [`sequence-publish.png`](sequence-publish.png) | Preview → apply анонімізації → gate → publish |
| Обмін | [`sequence-exchange.puml`](sequence-exchange.puml) / [`sequence-exchange.png`](sequence-exchange.png) | Запит → рішення провайдера → download clean-версії |

Діаграми побудовані в PlantUML. Перевірка та рендеринг:

```bash
java -jar plantuml.jar -checkonly docs/architecture/*.puml
java -jar plantuml.jar -tpng docs/architecture/*.puml
```

## 3. Backend: модулі

### 3.1. API-роутери

| Роутер | Префікс | Відповідальність |
|---|---|---|
| `routers/auth.py` | `/auth` | Вхід, поточний користувач |
| `routers/datasets.py` | `/datasets` | Завантаження, профіль, PII, правила якості |
| `routers/quality.py` | `/datasets/{id}/quality` | Quality API, перевірка правил, історія |
| `routers/publication.py` | `/datasets/{id}/anonymize`, `/publish`, `/versions` | Анонімізація та публікація |
| `routers/exchange.py` | `/exchange-requests` | Життєвий цикл запитів на доступ |
| `routers/catalog.py` | `/datasets` (published) | Каталог для Data Consumer |
| `routers/legal_basis.py` | `/datasets/{id}/legal-basis` | Правові підстави |
| `routers/audit.py` | `/audit` | Перегляд audit log (DataSteward) |

Усі публічні маршрути мають дубль із префіксом `/api` для сумісності з фронтендом і зовнішніми клієнтами. Дублі приховані з OpenAPI (`include_in_schema=False`).

### 3.2. Сервіси

| Сервіс | Призначення |
|---|---|
| `services/quality_service.py` | Розрахунок Quality Score, перевірка правил, історія |
| `services/pii_utils.py` | Нормалізація PII-знахідок, визначення активного PII |
| `services/anonymizer.py` | Preview/apply, маскування, узагальнення, HMAC |
| `services/publication_gate.py` | Перевірки перед публікацією, reason codes |
| `services/dataset_io.py` | Читання/запис CSV та JSON, контроль типів |
| `services/exchange_service.py` | Запити, рішення, перевірка мети й підстави, download |
| `services/legal_basis_service.py` | Створення, відкликання, валідація підстав |
| `profiler.py` | Профілювання колонок і виявлення PII |

### 3.3. Модель даних

Ключові таблиці:

- `users` — користувачі та ролі (`DataProvider`, `DataConsumer`, `DataSteward`);
- `datasets` — метадані набору, клас, статус публікації, `retention_until`;
- `dataset_versions` — незмінні raw/clean-знімки файлів із `sha256`;
- `anonymization_methods` — метод, застосований до PII-колонки;
- `legal_basis` — підстави (`consent`, `contract`, `law`), мета, строк дії, відкликання;
- `exchange_requests` — запити на доступ і рішення провайдера;
- `quality_rules`, `rule_violations` — правила якості та порушення;
- `audit_logs` — журнал дій без PII.

Деталі полів і зв’язків — на [діаграмі класів](class-diagram.puml).

## 4. Ключові потоки

### 4.1. Публікація

1. DataProvider завантажує файл → створюється `Dataset` і raw `DatasetVersion`.
2. Профілювання та PII review визначають активні PII-колонки.
3. `POST /datasets/{id}/anonymize/preview` показує очікуваний результат без запису.
4. `POST /datasets/{id}/anonymize` створює clean `DatasetVersion` і фіксує методи.
5. `GET /datasets/{id}/publish/check` перевіряє gate (read-only).
6. `POST /datasets/{id}/publish` публікує набір або повертає `422` з reason codes.

Reason codes publication gate:

| Код | Short code | Значення |
|---|---|---|
| `no_clean_version` | `no_clean` | Немає clean-версії |
| `pii_not_processed` | `pii_unprocessed` | Є непідтверджені/необроблені PII |
| `hmac_without_legal_basis` | `hmac_no_basis` | HMAC без чинної правової підстави |
| `retention_required` | `retention_req` | Не вказано `retention_until` |

Деталі — на [діаграмі публікації](sequence-publish.puml).

### 4.2. Обмін даними

1. DataConsumer бачить у каталозі лише опубліковані набори.
2. `POST /exchange-requests` створює запит зі статусом `Requested`.
3. Лише власник набору (DataProvider) може `approve` або `reject`.
4. Під час `approve` задається `access_until`.
5. `GET /exchange-requests/{id}/download` перевіряє статус, строк, мету та чинну правову підставу, після чого віддає clean-файл і переводить запит у `Downloaded`.
6. Прострочені запити стають `Expired`.

Деталі — на [діаграмі обміну](sequence-exchange.puml).

## 5. Безпека та governance

- RBAC перевіряється на рівні роутерів і сервісів; матриця — [`docs/testing/rbac-matrix.md`](../testing/rbac-matrix.md).
- PII не потрапляє в audit log: логуються ідентифікатори, коди причин і результати.
- HMAC-псевдонімізація потребує `HMAC_KEY`; у production використовується лише явно заданий ключ.
- Правова підстава перевіряється під час обміну, а не під час публікації.
- `retention_until` зберігається на наборі та передається під час publish.
- Усі рішення та відмови фіксуються подіями `REQUEST`, `REQUEST_APPROVED`, `REQUEST_REJECTED`, `DOWNLOAD`, `DENY`.

## 6. Розгортання

```bash
docker compose down -v
docker compose up --build -d
```

Сервіси:

- frontend — <http://localhost>;
- backend — <http://localhost:8000>;
- health — <http://localhost:8000/health>, <http://localhost:8000/health/db>.

Змінні середовища: `DATABASE_URL`, `SECRET_KEY`, `ENV`, `HMAC_KEY`, `STORAGE_DIR`. Демо-сценарій — [`docs/demo.md`](../demo.md).

## 7. Пов’язані документи

- [Демо-сценарій](../demo.md)
- [Sprint 3](../scrum/sprint-3.md)
- [Вимоги до governance](../governance/data-governance-requirements.md)
- [Матриця RBAC](../testing/rbac-matrix.md)
