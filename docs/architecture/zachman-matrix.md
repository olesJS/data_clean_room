# Матриця Захмана 6×6 для Data Clean Room

- **Задача:** SCRUM-60 (епік SCRUM-9 — E3 «Архітектура і UML»)
- **Версія:** 0.2 (чернетка)
- **Дата:** 12.11.2026
- **Автор:** Дмитро Петрунів (роль C — архітектор / data governance)
- **Статус:** чернетка; фіналізація після merge SCRUM-59 (PR #28) і SCRUM-64

## 1. Призначення та межі

Матриця Захмана описує прототип Data Clean Room (DCR) з шести перспектив і шести питань. Кожна клітинка посилається на **реальний артефакт репозиторію** — UC-специфікацію, діаграму, модель, код, тест або конфігурацію, — а не на приклад із методички. Якщо артефакту ще немає, клітинка явно позначає прогалину та залежність.

**Межі матриці:** MVP DCR — завантаження CSV/JSON, профілювання, виявлення PII, анонімізація, публікація з воротами, запит доступу, схвалення, завантаження clean-версії, аудит і retention. Поза межами: ABAC, синтетична заміна, e-signature, повна відповідність ISO 27001 (див. [governance §4](../governance/data-governance-requirements.md)).

**Легенда статусів:**

- ✅ — реалізовано в `main` або зафіксовано як робочий артефакт;
- 🟡 — реалізовано у відкритому PR (SCRUM-57/58) або є цільовою моделлю Спринту 3;
- ⏳ — заплановано, залежність вказана;
- ❌ — прогалина, потребує рішення або окремої задачі.

## 2. Стейкхолдери

| Стейкхолдер | Що для нього важливо | Рядки матриці |
|---|---|---|
| Власник продукту / організація-учасниця | межі MVP, вартість, відповідність вимогам | Scope, Business Model |
| Data Provider | контроль публікації, правова підстава, якість даних | Business Model, Functioning Enterprise |
| Data Consumer | пошук набору, запит доступу, отримання clean-версії | Business Model, Functioning Enterprise |
| Data Steward | метадані, журнал аудиту, якість, обробка відмов | Business Model, Functioning Enterprise |
| Суб'єкти даних | згода, мінімізація, видалення персональних даних | Scope, Business Model |
| Регулятор / Уповноважений ВРУ | законність підстави, підзвітність, обмеження зберігання | Scope, Why-колонка |
| Архітектор (C) | цілісність моделі та трасовність артефактів | System Model |
| Backend / Frontend / DevOps (D, E) | реалізація, середовище, експлуатація | Technology Model |
| Розробники / QA (A) | тести, негативні кейси, трасовність до UC | Detailed Representations |

## 3. Рядки та колонки

**Рядки (перспективи):**

1. **Scope (контекст)** — межі системи та організації-учасниці.
2. **Business Model (концептуальна)** — бізнес-сутності, процеси, ролі, події.
3. **System Model (логічна)** — логічна архітектура, модель даних, сервіси, правила.
4. **Technology Model (фізична)** — технології, середовище розгортання, фізичні обмеження.
5. **Detailed Representations (детальна)** — код, DDL, конфігурації, тести.
6. **Functioning Enterprise (робоча)** — реальні дані, демо-сценарій, експлуатація.

**Колонки (питання):** What (дані), How (процеси), Where (мережа/розташування), Who (люди), When (час), Why (мотивація).

## 4. Матриця 6×6

| Перспектива | What — дані | How — процеси | Where — мережа | Who — люди | When — час | Why — мотивація |
|---|---|---|---|---|---|---|
| **1. Scope (контекст)** | Табличні набори CSV/JSON із PII, реєстр правових підстав, журнал аудиту. → [UC-01–UC-13](../requirements/UC_Specifications_DCR.docx), [data/](../../data/) ✅ | Повний цикл: завантаження → профілювання → PII → анонімізація → публікація → запит → схвалення → завантаження. → [Use Case Diagram](../requirements/Use_Case_Diagram_DCR.docx), [README](../../README.md) ✅ (опис), 🟡 (код) | Організації-учасниці в одному ізольованому середовищі DCR; локальний Docker-стенд. → [docker-compose.yml](../../docker-compose.yml) ✅ | Provider, Consumer, Steward; суб'єкти даних; регулятор. → [UC-01–UC-13](../requirements/UC_Specifications_DCR.docx) ✅ | Життєвий цикл набору: upload → publish → request → approve → download → expire; терміни зберігання. → [UC-13](../requirements/UC_Specifications_DCR.docx) ✅ (опис), ⏳ (retention) | Безпечний обмін без розкриття PII; Закон України №2297-VI, GDPR. → [governance §2](../governance/data-governance-requirements.md) ✅ |
| **2. Business Model (концептуальна)** | Dataset, DatasetVersion, LegalBasis, ExchangeRequest, AuditLog; класи Public/Internal/Confidential/Personal. → [class-diagram.puml](class-diagram.puml), [governance §3.1](../governance/data-governance-requirements.md) ✅ (модель), ⏳ (DatasetVersion/ExchangeRequest у БД) | Публікація з воротами; запит доступу; схвалення/відмова лише власником набору (`DataProvider`, UC-09 EX1); видалення за retention. → [UC-07–UC-13](../requirements/UC_Specifications_DCR.docx), [sequence-publish.puml](sequence-publish.puml), [sequence-exchange.puml](sequence-exchange.puml) ✅ (опис), 🟡 (publish gate) | Каталог наборів; сховище clean-версій; журнал аудиту. → [governance §3.2](../governance/data-governance-requirements.md) ✅ (правила), ⏳ (каталог UI) | Актори UC + системний планувальник retention. → [Use Case Diagram](../requirements/Use_Case_Diagram_DCR.docx), [UC-13](../requirements/UC_Specifications_DCR.docx) ✅ | Події PUBLISH, REQUEST, REQUEST_APPROVED, REQUEST_REJECTED, DOWNLOAD, EXPIRE; відмова через підставу — DENY. → [UC-09, UC-10, UC-13](../requirements/UC_Specifications_DCR.docx) ✅ (опис), ⏳ (код) | Мінімізація, обмеження зберігання, підзвітність, правова підстава. → [governance §3.3–3.6](../governance/data-governance-requirements.md) ✅ |
| **3. System Model (логічна)** | Логічна схема: users, datasets, legal_basis, audit_logs; data_class, quality_score, profile_json, pii_json. → [models.py](../../backend/app/models.py) ✅; purpose/valid_until/revoked_* 🟡 PR #29 | FastAPI-роутери auth/datasets/legal_basis/audit; profiler + quality_engine; майбутній exchange_service. → [routers](../../backend/app/routers), [services](../../backend/app/services) ✅/⏳ | React SPA → FastAPI → PostgreSQL; файли в storage/ і data/. → [README](../../README.md), [docker-compose.yml](../../docker-compose.yml) ✅ | JWT HS256 + bcrypt; RBAC трьох ролей; матриця доступу; approve/reject — лише `DataProvider`-власник. → [auth.py](../../backend/app/auth.py), [governance §3.2](../governance/data-governance-requirements.md) ✅ | created_at, valid_until, revoked_at; статуси запиту `Requested → Approved / Rejected → Downloaded`, `Expired` за `access_until`; retention_until. → [models.py](../../backend/app/models.py) ✅/🟡/⏳ | Publication gate (SCRUM-54/55/57), check_legal_basis (SCRUM-58), YAML-правила якості. → [sequence-publish.puml](sequence-publish.puml), [PR #30](https://github.com/olesJS/data_clean_room/pull/30) 🟡 |
| **4. Technology Model (фізична)** | PostgreSQL 15; enum-типи; SQLAlchemy-моделі; SQLite для тестів. → [models.py](../../backend/app/models.py), [docker-compose.yml](../../docker-compose.yml) ✅ | Python 3.11 / FastAPI / SQLAlchemy; React 18 / Vite / TypeScript; nginx; pytest / ruff; GitHub Actions. → [requirements.txt](../../backend/requirements.txt), [package.json](../../frontend/package.json), [ci.yml](../../.github/workflows/ci.yml) ✅ | Docker Compose: frontend :80, backend :8000, db :5432, volume postgres_data. → [docker-compose.yml](../../docker-compose.yml) ✅; uploads volume ❌ (SCRUM-71) | users + JWT + ролі; seed-користувачі для dev/test. → [auth.py](../../backend/app/auth.py), [database.py](../../backend/app/database.py) ✅ | UTC-таймстемпи; CI на push/PR; фоновий retention. → [models.py](../../backend/app/models.py), [ci.yml](../../.github/workflows/ci.yml) ✅/⏳ | HMAC-SHA256 (псевдонімізація), YAML-правила, аудит. → [profiler.py](../../backend/app/profiler.py), [quality_engine.py](../../backend/app/services/quality_engine.py) 🟡/⏳; HMAC ❌ |
| **5. Detailed Representations (детальна)** | DDL/міграції: Alembic відсутній (SCRUM-42); таблиці створює Base.metadata.create_all; поля та індекси. → [database.py](../../backend/app/database.py) ✅/❌ | Код роутерів/сервісів і тести: RBAC, legal basis, quality, profiler, e2e. → [tests](../../backend/tests) ✅ | Dockerfile backend/frontend, nginx.conf, .env.example, порти. → [backend/Dockerfile](../../backend/Dockerfile), [frontend/Dockerfile](../../frontend/Dockerfile) ✅ | RBAC-матриця трьох ролей; JWT-тести; seed users. → [test_rbac_matrix.py](../../backend/tests/test_rbac_matrix.py) ✅ | Тести аудиту/таймстемпів; retention-тести. → [test_hardcore_verification.py](../../backend/tests/test_hardcore_verification.py) ✅/⏳ | Тести Quality Score, legal basis, негативні кейси, аудит відмов. → [test_quality_engine.py](../../backend/tests/test_quality_engine.py), [PR #30](https://github.com/olesJS/data_clean_room/pull/30) ✅/🟡 |
| **6. Functioning Enterprise (робоча)** | Реальні набори: payroll.csv (500 рядків, 8 дефектів), customers.json (1000, 8 дефектів), PII benchmark. → [data/](../../data/), [defects.md](../../data/defects.md) ✅ | Демо-сценарій: login → upload → profile → PII → quality → publish → request → approve → download → audit. → [test_e2e_scenario.py](../../backend/tests/test_e2e_scenario.py), [test-cases-uc01-uc02.md](../testing/test-cases-uc01-uc02.md) ✅/⏳ | Розгорнутий стенд `docker compose up --build -d`: localhost, :8000, :5432. → [README](../../README.md) ✅ | Реальні облікові записи трьох ролей; UI: login/upload/datasets/profile/PII/quality ✅; catalog/requests/access/audit — заглушки. → [App.tsx](../../frontend/src/App.tsx), [pages](../../frontend/src/pages) ✅/⏳ | Аудит в API ✅; журнал в UI — заглушка; retention/expire — ⏳. → [audit.py](../../backend/app/routers/audit.py), [AuditPage.tsx](../../frontend/src/pages/AuditPage.tsx) | Демонстрація Quality Score 91.8/87.0, відмов, аудиту; метрики. → [test-cases-uc03-uc05.md](../testing/test-cases-uc03-uc05.md) ✅ |

> **Важливо:** `class-diagram.puml` — цільова модель Спринту 3. Сутності `DatasetVersion`, `ExchangeRequest`, `Policy`, `QualityRule`, `RuleViolation`, `AnonymizationMethod` ще не мають відповідних таблиць у `models.py`; вони позначені як ⏳ і закриваються задачами SCRUM-54/55/56. `AuditEvent` на діаграмі відповідає таблиці `audit_logs` у коді.

## 5. Перевірка узгодженості

| № | Перевірка | Статус | Доказ | Власник | Наступний крок |
|---|---|---|---|---|---|
| 1 | Кожна роль з `Who` має UC у `How` | ✅ | Provider, Consumer, Steward присутні в UC-01–UC-13 | B / C | Після SCRUM-64 звірити Activity-діаграми з UC |
| 2 | Кожна сутність `What` має місце зберігання в `Where` | 🟡 | users, datasets, legal_basis, audit_logs → PostgreSQL; DatasetVersion, ExchangeRequest ще не в моделях | D | SCRUM-56: додати моделі та міграцію |
| 3 | Кожне правило `Why` має тест у `Detailed` | ✅ / 🟡 | Quality Score, legal basis, RBAC — є тести; publication gate — ще ні | A / C | SCRUM-54/55/57: тести воріт |
| 4 | Кожен статус `When` має відображення в БД/аудиті | 🟡 | LOGIN, UPLOAD, DENY, CREATE_LEGAL_BASIS, CONSENT_REVOKED ✅; PUBLISH, REQUEST, REQUEST_APPROVED, REQUEST_REJECTED, DOWNLOAD, EXPIRE, DELETE ⏳ | D | SCRUM-54/56: події та статуси |
| 5 | Кожен компонент `Where` є в `docker-compose.yml` | ✅ / ❌ | frontend, backend, db ✅; uploads volume ❌ | D | SCRUM-71: додати volume для uploads |
| 6 | Кожна клітинка має артефакт або позначена як прогалина | ✅ | 36/36 клітинок заповнено | C | Підтримувати під час змін архітектури |

## 6. Прогалини та план закриття

| № | Клітинка | Прогалина | Залежність | Власник | Критерій закриття |
|---|---|---|---|---|---|
| 1 | Business / What; System / What | `DatasetVersion`, `ExchangeRequest` відсутні в БД | SCRUM-56 | Nazar / D | Моделі, міграція, тести, оновлена class-діаграма |
| 2 | System / How | Немає `exchange_service` (approve/download) | SCRUM-56 | Nazar / D | Ендпоінти + аудит `DENY` з `legal_basis_invalid` |
| 3 | System / Why | Немає `publication_gate` | SCRUM-54/55/57 | C / D | Ворота + тести + `PUBLISH` в аудиті |
| 4 | Technology / Why | Немає anonymizer/HMAC-сервісу | SCRUM-55 | D | Сервіс псевдонімізації + тести |
| 5 | Detailed / What | Немає Alembic-міграцій | SCRUM-42 | Nazar | Baseline-міграція та CI-перевірка |
| 6 | Detailed / Why | Немає тестів publication gate | SCRUM-54/55/57 | A / C | Покриття всіх чотирьох умов воріт |
| 7 | Functioning / Who | Catalog, Requests, Access, Audit UI — заглушки | Frontend Спринту 3 | E | Сторінки підключені до API |
| 8 | Functioning / When | Немає планувальника retention | SCRUM-13/41 | D | Фонове завдання + `EXPIRE`/`DELETE` в аудиті |
| 9 | Technology / Where | Немає volume для uploads | SCRUM-71 | D | Volume у compose + README |

## 7. Артефакти та посилання

| Артефакт | Роль у матриці | Статус |
|---|---|---|
| [UC_Specifications_DCR.docx](../requirements/UC_Specifications_DCR.docx) | What / How / Who / When | ✅ |
| [Use_Case_Diagram_DCR.docx](../requirements/Use_Case_Diagram_DCR.docx), [PNG](../requirements/use_case_diagram.png) | How / Who | ✅ |
| [class-diagram.puml](class-diagram.puml), [PNG](class-diagram.png) | Business / System / What | ✅ (цільова модель) |
| [sequence-exchange.puml](sequence-exchange.puml) | How / When / Why | 🟡 PR #28 |
| [sequence-publish.puml](sequence-publish.puml) | How / Why | 🟡 PR #28 |
| [diagram-consistency.md](diagram-consistency.md) | Перевірка узгодженості | 🟡 PR #28 |
| [data-governance-requirements.md](../governance/data-governance-requirements.md) | Why / Where / When | ✅ |
| [models.py](../../backend/app/models.py) | System / What | ✅ / 🟡 PR #29 |
| [routers/](../../backend/app/routers), [services/](../../backend/app/services) | System / How | ✅ / 🟡 |
| [frontend/src/](../../frontend/src) | Who / Functioning | ✅ / ⏳ |
| [docker-compose.yml](../../docker-compose.yml) | Where / Technology | ✅ |
| [.github/workflows/ci.yml](../../.github/workflows/ci.yml) | Detailed | ✅ |
| [data/](../../data/) | Functioning / What | ✅ |
| [backend/tests/](../../backend/tests) | Detailed / Why | ✅ / 🟡 |

## 8. Журнал змін

| Версія | Дата | Зміна | Автор |
|---|---|---|---|
| 0.1 | 10.11.2026 | Перша чернетка 6×6; зафіксовано 9 прогалин і залежності від SCRUM-42/54/55/56/57/64/71 | Дмитро Петрунів |
| 0.2 | 12.11.2026 | Узгоджено з рішеннями PO для PR #28: approve/reject лише `DataProvider`-власник; події `REQUEST_APPROVED`/`REQUEST_REJECTED`; статуси `Requested → Approved / Rejected → Downloaded`, `Expired` за `access_until` | Дмитро Петрунів |
