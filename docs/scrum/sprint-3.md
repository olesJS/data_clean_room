# Спринт 3: Planning, Review, Retrospective

Проєкт: Data Clean Room · Jira: SCRUM · Scrum-майстер: Якимчук Олексій · Product Owner: Петрунів Дмитро

## 1. Параметри Спринта 3

| Параметр | Значення |
| --- | --- |
| Планові дати | **16.11 – 06.12.2026** |
| Фактична робота | 09.11 – 12.11.2026 (інтеграційна гілка `feature/sprint-3-demo`) |
| Мета | Завершити базову архітектуру обміну даними, ворота публікації та управління згодою; довести прототип до демонстраційного стану |
| Основні задачі | SCRUM-52, SCRUM-53, SCRUM-54, SCRUM-55, SCRUM-56, SCRUM-57, SCRUM-58 |
| Документація / UML | SCRUM-59, SCRUM-60, SCRUM-71 (stretch) |
| UI | SCRUM-62 (публікація), SCRUM-63 (каталог і запити), аудит, правова підстава |

## 2. Мета Спринта 3

> Data Provider може безпечно підготувати й опублікувати набір: переглянути PII, зареєструвати правову підставу, виконати preview та apply анонімізації, пройти publication gate. Data Consumer бачить лише опубліковані набори, створює запит на доступ, а власник набору схвалює або відхиляє його. Завантажується лише clean-версія. Усі дії та відмови потрапляють в аудит без PII.

**Що показуємо на Sprint Review:** сценарій з [docs/demo.md](../demo.md) — від завантаження `payroll.csv` до завантаження очищеного файлу Consumer і перегляду журналу аудиту Steward.

## 3. Рішення Product Owner, зафіксовані в реалізації

| № | Рішення |
| --- | --- |
| 1 | `approve`/`reject` ухвалює **лише власник набору** (DataProvider); Data Steward бачить чергу, але не ухвалює рішень |
| 2 | Статуси запиту: `Requested → Approved | Rejected | Downloaded | Expired`; `access_until` задає межі доступу |
| 3 | Події аудиту: `REQUEST`, `REQUEST_APPROVED`, `REQUEST_REJECTED`, `DOWNLOAD`, `DENY` (зокрема `legal_basis_invalid`) |
| 4 | `GET /publish/check` — **read-only** і приймає `retention_until`; не змінює набір |
| 5 | Клас після публікації: без PII → `Internal`; mask/generalize/redact → `Confidential`; HMAC → `Personal` |
| 6 | Анонімізація має окремі **preview (без запису)** та **apply (clean DatasetVersion)** |
| 7 | Мета обробки перевіряється під час exchange (створення, схвалення, завантаження), а не під час публікації |
| 8 | Чужий або неіснуючий об’єкт для Provider — `404`, а не `403`, щоб не розкривати існування |
| 9 | Причини publication gate: `no_clean_version`, `pii_not_processed`, `hmac_without_legal_basis`, `retention_required` |
| 10 | HMAC без чинної правової підстави блокує публікацію; відкликання підстави блокує нові схвалення й завантаження |

## 4. Sprint Backlog і результат

### 4.1. Backend і governance

| Задача | Пріоритет | Результат |
| --- | --- | --- |
| SCRUM-52: Consumer не бачить сирих наборів | P0 | `GET /datasets` фільтрує `status=published`; тест без `xfail`; оновлено `docs/testing/rbac-matrix.md` |
| SCRUM-53: Quality API | P0 | `GET /api/datasets/{id}/quality-rules` і `.../quality-violations`; тести на payroll/customers, RBAC, 404 |
| SCRUM-54: версії набору | P0 | `DatasetVersion` (`raw`/`clean`, `version_number`, `sha256`, `row_count`); без Alembic — `create_all`/свіжий volume |
| SCRUM-55: анонімізація | P0 | `preview`/`apply`, `AnonymizationMethod`, методи mask/generalize/hmac/redact, захист від невідомих колонок |
| SCRUM-56: exchange flow | P0 | Модель `ExchangeRequest`, сервіс життєвого циклу, API create/list/get/approve/reject/download, RBAC і аудит |
| SCRUM-57: publication gate + consent | P0 | `publication_gate.py`, `POST /publish`, `GET /publish/check`, retention, перерахунок класу; реєстр підстав із `purpose`/`valid_until`/revoke |
| SCRUM-58: чинність підстави | P0 | `check_legal_basis` з reasons `no_legal_basis`, `revoked`, `expired`, `purpose_mismatch`; причини scoped до мети |
| SCRUM-33: RBAC-матриця | P1 | Оновлено матрицю доступу; `GET /catalog` для Consumer/Steward; тести ролей |

### 4.2. Frontend

| Екран | Маршрут | Результат |
| --- | --- | --- |
| Журнал аудиту | `/audit` | Таблиця з фільтрами за дією/результатом і пошуком; Steward-only |
| Каталог | `/catalog` | Лише опубліковані набори; Consumer створює запит із вибором мети; Steward бачить метадані |
| Мої запити | `/requests` | Статуси, мета, `access_until`, коментар; завантаження clean-файлу |
| Запити на доступ | `/access` | Черга Provider; схвалення з датою доступу або відхилення з причиною |
| Публікація | `/datasets/:id/publish` | PII-методи, preview/apply, publication gate, версії, правові підстави |
| Правові підстави | `/datasets/:id/legal` | Реєстр, створення, відкликання; активні/відкликані/прострочені |
| Набори | `/datasets` | Дії «Профіль» і «Публікація»; статуси з бекенду нормалізовано |

### 4.3. Документація, демо, інфраструктура

| Артефакт | Стан |
| --- | --- |
| `docs/demo.md` | Сценарій демо, негативні кейси, API-приклади, troubleshooting |
| `scripts/demo_seed.py` | Через публічний API створює 2 опубліковані набори та схвалений запит |
| `docs/scrum/sprint-3.md` | Цей документ |
| Governance | Синхронізовано розділи 3.2–3.5 з фактичними статусами, подіями, причинами gate |
| Docker | Додано том для `/app/storage` і `HMAC_KEY`; свіжий `down -v` створює схему |
| UML | `class-diagram.puml`, `sequence-exchange.puml`, `sequence-publish.puml` + PNG (перевірка `plantuml -checkonly`) |

## 5. Стан інтеграції та PR

Робота Спринта 3 зібрана в інтеграційній гілці `feature/sprint-3-demo` поверх `main` (`1aefcf5`). Гілка містить cherry-pick комітів PR #29 (consent/legal basis) і PR #30 (legal basis check), а також нову реалізацію Sprint 3.

| PR | Стан | Що це означає |
| --- | --- | --- |
| #28 | `CHANGES_REQUESTED` | UML/README не можна зливати без повторного рев’ю |
| #29 | `CHANGES_REQUESTED` | Consent/legal basis не можна зливати без повторного рев’ю |
| #30 | Без approval | Legal basis check не можна зливати без рев’ю |
| #31 | Draft | Zachman/документація не готова до merge |
| — | `feature/sprint-3-demo` | Інтеграційна гілка для демо; **не злита в `main`**, бо немає APPROVED review |

Правило процесу: жоден PR не зливається без щонайменше одного `APPROVED` рев’ю. Інтеграційна гілка не пушиться й не замінює рев’ю.

## 6. Sprint Review

**Мету спринта досягнуто для демонстраційного стану.**

Що показано:
- повний ланцюг `upload → PII review → legal basis → anonymize preview/apply → publish gate → publish`;
- каталог лише з опублікованими наборами; запит Consumer, рішення власника, завантаження clean-версії;
- аудит усіх дій і відмов без PII; окремі події `REQUEST`, `REQUEST_APPROVED`, `REQUEST_REJECTED`, `DOWNLOAD`, `DENY`;
- Quality API та RBAC-матриця без відомого дефекту SCRUM-52;
- 232 backend-тести, `ruff`, `npm run lint` (0 warnings), `npm run build`, Docker smoke.

Що має застереження:
- PR #28–#31 не злиті: немає `APPROVED` рев’ю;
- Alembic не підключено: зміни схеми застосовуються на свіжій БД (`docker compose down -v`) або через `create_all`;
- у production обов’язковий `HMAC_KEY`, інакше HMAC-анонімізація не запускається;
- PII-детектор, як і в Спринті 2, має обмежений recall на нейтральних назвах колонок;
- UI-екрани покривають основний демо-потік, але не є фінальним дизайном Figma.

## 7. Retrospective

**Що працювало добре:**
- Контракт «preview без запису → apply» зменшив ризик випадкової публікації.
- Стабільні коди причин gate (`no_clean_version` тощо) спростили тести й UI.
- Окремі сервіси (`publication_gate`, `exchange_service`, `legal_basis_service`) дали чіткі межі відповідальності.
- Негативні тести (revoked basis, purpose mismatch, expired access, чужий Provider) знайшли реальні крайові випадки.

**Що покращити:**
- Додати Alembic до наступного спринту: зараз кожна зміна схеми вимагає свіжої БД.
- Прибрати дублювання `/api`-аліасів через єдиний префікс або nginx-правило.
- Додати інтеграційні тести UI (Playwright) для демо-потоку.
- Зменшувати кількість `useEffect`-залежностей у нових екранах: lint уже без попереджень, але варто винести завантаження даних у спільні хуки.
- Зафіксувати в Jira фактичні дати завершення задач і додати скриншоти Sprint Review.

## 8. Definition of Done Спринта 3

- [x] Publication gate перевіряє clean-версію, PII, HMAC і retention.
- [x] Клас перераховується за рішенням PO.
- [x] Preview не створює файлів/версій; apply створює незмінну clean-версію.
- [x] Consumer бачить лише опубліковані набори.
- [x] Запит проходить `Requested → Approved/Rejected → Downloaded/Expired`.
- [x] Рішення ухвалює лише власник; Steward не має права рішення.
- [x] Завантажується лише clean-версія; сирий файл недоступний.
- [x] Відкликана/прострочена підстава блокує нові схвалення й завантаження.
- [x] Усі дії та відмови пишуться в аудит без PII.
- [x] RBAC-матриця та SCRUM-52 оновлені.
- [x] `pytest`, `ruff`, `npm run lint`, `npm run build`, Docker smoke зелені.
- [x] Є демо-сценарій, seed-скрипт і документація.
- [ ] PR #28–#31 злиті в `main` — **заблоковано відсутністю APPROVED review**.

## 9. Посилання

- [Демо-сценарій](../demo.md)
- [Матриця RBAC](../testing/rbac-matrix.md)
- [Governance-вимоги](../governance/data-governance-requirements.md)
- [Архітектура та UML](../architecture/README.md)
- [Sprint 2](sprint-2.md)
