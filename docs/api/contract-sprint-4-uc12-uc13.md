# Контракт API Спринта 4: картка набору (UC-12) і видалення після терміну (UC-13)

- **Задача:** SCRUM-76 (епік SCRUM-9)
- **Автор:** Дмитро Петрунів (Роль C — Архітектор)
- **Версія:** 1.0 · 27.11.2026 · дедлайн фіксації — 29.11.2026
- **Для кого:** Назар (SCRUM-81 — UC-13 backend, SCRUM-82 — поля картки API), Софія (SCRUM-84 — UI картки, SCRUM-85 — опис і семантика в UI, SCRUM-86 — UI для UC-13); частково SCRUM-89 (тест-кейси) і SCRUM-99 (діаграми)
- **Джерела:** специфікації UC-12, UC-13 (`docs/requirements/UC_Specifications_DCR.docx`); [data-governance-requirements.md](../governance/data-governance-requirements.md), розділи 3.2, 3.4, 3.6; [data-dictionary.md](../governance/data-dictionary.md), розділ 1.2; ADR-002 (SCRUM-77), рішення 5; [rbac-matrix.md](../testing/rbac-matrix.md)

## 0. Як працюємо з контрактом

Навіщо: у Спринті 3 контракт не узгодили заздалегідь, і UI переробляли під фактичні відповіді (ретро Спринта 3, [sprint-3.md](../scrum/sprint-3.md), розділ 10).

1. Цей документ — джерело істини. У коментарях до SCRUM-81, 82, 84, 85, 86 — короткий виклад і посилання на розділ.
2. Назар і Софія підтверджують контракт коментарем у своїх задачах («Контракт v1.0 прочитав(ла), погоджую» або питання).
3. Будь-яка зміна після 29.11 — лише через PR у цей файл з новою версією в розділі 9 **і** коментарем в обох задачах (backend і frontend). Мовчазні зміни в коді, що розходяться з контрактом, — дефект.
4. Порядок перевірок для всіх нових ендпоінтів той самий, що в Спринті 3: `401` (немає токена) → `403` (роль не має права) → `404` (неіснуючий або чужий ресурс, рішення PO №8) → `409` / `410` / `422` (стан і валідація).

Ролі в таблицях доступу: **Owner** — `DataProvider`, власник набору (`uploaded_by`); **Foreign** — інший `DataProvider`; **Consumer** — `DataConsumer`; **Steward** — `DataSteward`.

## 1. Зміни моделі даних (SCRUM-81, SCRUM-82)

Одна Alembic-міграція на кожну задачу (або одна спільна, якщо Назар робить обидві разом).

### 1.1. `Dataset` — нові поля

| Поле | Тип БД | Null | Обмеження | Хто заповнює | Задача |
| --- | --- | --- | --- | --- | --- |
| `description` | `Text` | так | до 2000 символів після `strip()` | Provider (`PATCH /metadata`) | SCRUM-82 |
| `column_semantics` | `JSON` | так | `{колонка: опис}`; ключі — лише з `columns`; значення 1–300 символів | Provider (`PATCH /metadata`) | SCRUM-82 |
| `expired_at` | `DateTime` (UTC) | так | заповнюється при переході в `expired` | Система | SCRUM-81 |
| `expired_by` | `String(255)` | так | `scheduler` або email Steward | Система | SCRUM-81 |

`status` (рядок, без enum у БД) отримує нове значення: `uploaded` → `published` → **`expired`**. Інших переходів немає: `expired` — кінцевий стан.

### 1.2. `ExchangeRequestStatus` — нове значення

`pending`, `approved`, `rejected`, `downloaded`, **`expired`**. У PostgreSQL це `exchange_request_status_enum`, тож міграція робить `ALTER TYPE ... ADD VALUE 'expired'`.

Переходи в `expired` — лише з `pending`, `approved`, `downloaded` і лише разом з набором. `rejected` не змінюється.

### 1.3. Що не змінюється

`DatasetVersion`, `AnonymizationMethod`, `LegalBasis`, `AuditLog` — без нових колонок. Після видалення файлів записи `dataset_versions` лишаються (lineage), поле `file_path` не очищується, але файла за ним немає.

## 2. UC-13: ручне видалення Steward'ом (AC1)

### `POST /api/datasets/{id}/expire`

Достроково видаляє файли сирої і очищеної версій, переводить набір і відкриті запити в `expired`. Ті самі кроки, що виконує планувальник (розділ 3), але для одного набору і з ініціатором — email Steward.

**Доступ**

| Без токена | Owner | Foreign | Consumer | Steward |
| --- | --- | --- | --- | --- |
| 401 | 403 | 403 | 403 | 200 |

Роль перевіряється до пошуку набору, тому Owner і Foreign отримують однаковий 403 (як `approve` для не-Provider). Неіснуючий набір для Steward — 404.

**Тіло запиту:** порожнє (`{}` або без тіла). Причину дострокового видалення в MVP не зберігаємо.

**Відповідь 200**

```json
{
  "dataset_id": 12,
  "status": "expired",
  "expired_at": "2026-12-01T10:15:03",
  "expired_by": "steward@example.com",
  "deleted_versions": [
    { "version_id": 31, "kind": "raw" },
    { "version_id": 32, "kind": "clean" }
  ],
  "expired_requests": [7, 9]
}
```

- `deleted_versions` — версії, файли яких видалено в цьому запуску. Якщо файлу вже не було (UC-13, EX2), версії в списку немає, але набір однаково переходить у `expired`.
- `expired_requests` — id запитів, що перейшли в `expired` (може бути `[]`).

**Коди відповідей**

| Код | Коли | `detail` |
| --- | --- | --- |
| 200 | Видалено, статус `expired` | — |
| 401 | Немає / недійсний токен | як зараз |
| 403 | Роль не `DataSteward` | `Only DataSteward can expire datasets` |
| 404 | Набору не існує | `Dataset not found.` |
| 409 | Набір `uploaded` (не опублікований, терміну зберігання немає) | `Only published datasets can be expired` |
| 409 | Набір уже `expired` | `Dataset is already expired` |
| 500 | Файл не вдалося видалити (сховище недоступне, EX1). Статус набору **не змінено** | `Storage error: dataset files were not deleted` |

**Аудит** (розділ 5): `DELETE` на кожен видалений файл, `EXPIRE` на набір і кожен запит, `actor` — email Steward. Відмови: 403 → `ACCESS_DENIED` / `FORBIDDEN`; 404 → `EXPIRE` / `FAILURE`; 409 → `EXPIRE` / `CONFLICT`; 500 → `DELETE` / `FAILURE`.

## 3. UC-13: планувальник

| Що | Рішення |
| --- | --- |
| Де працює | **У процесі backend** (контейнер `backend`), окремого сервісу в `docker-compose.yml` немає |
| Як запускається | `asyncio`-задача, яку стартує `lifespan` у `app/main.py`: **один запуск при старті** застосунку, далі **кожні `RETENTION_CHECK_INTERVAL_SECONDS`** (за замовчуванням `3600`). Без нових залежностей (APScheduler не потрібен) |
| Вимкнення | `RETENTION_SCHEDULER_ENABLED=false` — у тестах (`conftest.py`) і за потреби локально. За замовчуванням `true` |
| Ручний запуск усього завдання | `docker compose exec backend python -m app.services.retention` — один прохід по всіх наборах і вихід (для демо і перевірки без очікування інтервалу) |
| Код | Сервіс `app/services/retention.py` з однією функцією, яку викликають і планувальник, і `POST /expire`, наприклад `expire_dataset(db, dataset, initiator) -> ExpireResult` і `run_retention(db, today, initiator="scheduler") -> list[ExpireResult]` |
| Вибір наборів | `status = 'published' AND retention_until < today` (дата UTC). `retention_until` — останній день доступності |
| Порядок для одного набору | 1) видалити файли версій (`raw`, `clean`) і `Dataset.file_path`, якщо він не збігається з файлом версії; 2) лише якщо всі файли видалено або їх уже не було — `status='expired'`, `expired_at`, `expired_by`; 3) відкриті запити → `expired`; 4) аудит. Кроки 2–3 — в одній транзакції |
| Помилка сховища (EX1) | Статус не змінюється, `DELETE` / `FAILURE`, інші набори обробляються далі; наступний запуск повторює спробу |
| Ідемпотентність | `expired`-набори не вибираються; повторний запуск нічого не змінює |
| Кілька реплік backend | Не підтримуємо в MVP (один контейнер). Операції ідемпотентні, тож подвійний запуск не шкодить |

Нові змінні середовища додати в `.env.example` і README: `RETENTION_SCHEDULER_ENABLED`, `RETENTION_CHECK_INTERVAL_SECONDS`.

## 4. UC-13: поведінка існуючих ендпоінтів для `expired`

| Ендпоінт | Owner | Foreign | Consumer | Steward |
| --- | --- | --- | --- | --- |
| `GET /api/datasets` | бачить свій набір, `status: "expired"` | не бачить | не бачить (лише `published`) | бачить, `status: "expired"` |
| `GET /api/catalog` | не показується (каталог — лише `published`) | не показується | не показується | не показується |
| `GET /api/catalog/{id}` (розділ 6.3) | 200, картка зі `status: "expired"` | 404 | 404 | 200 |
| `GET /api/datasets/{id}/profile`, `/pii`, `/quality-rules`, `/legal-basis` | 200 — лише збережене в БД (див. нижче) | 404 | 403 | 200 |
| `GET /api/datasets/{id}/quality-violations` | **409** `Dataset is expired` | 404 | 403 | **409** |
| `POST /api/datasets/{id}/anonymize/preview`, `/anonymize`, `GET /publish/check`, `POST /publish` | **409** `Dataset is expired` | 404 | 403 | 403 |
| `POST /api/datasets/{id}/legal-basis` | **409** `Dataset is expired` | 404 | 403 | **409** |
| `POST /api/requests` (`dataset_id` expired) | — | — | 404 `Published dataset {id} not found` (як для неопублікованого) | — |
| `GET /api/requests` | запити зі `status: "expired"` | — | свої запити зі `status: "expired"` | усі, включно з `expired` |
| `POST /api/requests/{id}/approve`, `/reject` (запит `expired`) | **409** `Request is already resolved with status expired` | 404 | 403 | 403 |
| `GET /api/requests/{id}/download` (запит `expired`) | 404 | 404 | **410** (автор запиту) | 404 |

**Метадані `expired`-набору.** Після видалення файлів ендпоінти, що читають файл, не працюють, а ті, що читають БД, — працюють:

- `/profile` і `/pii` віддають **лише збережене в БД** (`profile_json`, `pii_json` з маскованими прикладами); файл не перечитується і профіль не перераховується.
- `/quality-rules` — правила з YAML, файл набору не потрібен, 200.
- `/quality-violations` рахує порушення з файлу, тому для `expired` — **409** `Dataset is expired` (а не 404 «файл не знайдено» і не 200). Аудит — як для інших відмов цього ендпоінта, `result=CONFLICT`.
- `/legal-basis` — записи реєстру з БД, 200.

### `GET /api/requests/{id}/download` для `expired`

```http
HTTP/1.1 410 Gone
Content-Type: application/json

{ "detail": "Dataset expired: retention period ended, files were deleted" }
```

- Порядок: 404 (чужий / неіснуючий запит) → **410** (запит `expired`) → 403 (запит не `approved` / `downloaded`) → 403 (підстава недійсна).
- Аудит: `DENY`, `object=request:{id}:expired`, `result=FAILURE` (UC-13, EX3).
- Чому 410, а не 403: UI має показати інше повідомлення («Набір видалено після терміну зберігання»), ніж для відмови за підставою. 410 означає, що ресурс був і більше не буде доступний.

## 5. UC-13: події аудиту

Формат запису не змінюється (`actor`, `action`, `object`, `result`; колонки `details` у `audit_logs` немає).

| `action` | `actor` | `object` | `result` | Коли |
| --- | --- | --- | --- | --- |
| `DELETE` | `scheduler` або email Steward | `dataset:{id}:version:{version_id}:{raw\|clean}` | `SUCCESS` | Файл версії видалено |
| `DELETE` | те саме | те саме | `FAILURE` | Файл не вдалося видалити (EX1) |
| `EXPIRE` | те саме | `dataset:{id}` | `SUCCESS` | Набір перейшов у `expired` |
| `EXPIRE` | те саме | `request:{id}` | `SUCCESS` | Запит перейшов у `expired` |
| `EXPIRE` | email Steward | `dataset:{id}` | `FAILURE` / `CONFLICT` | `POST /expire`: 404 / 409 |
| `DENY` | email Consumer | `request:{id}:expired` | `FAILURE` | Завантаження після видалення (410) |
| `ACCESS_DENIED` | email | шлях запиту | `FORBIDDEN` | `POST /expire` не від Steward |

Приклад журналу після ручного видалення:

```json
[
  { "actor": "steward@example.com", "action": "DELETE", "object": "dataset:12:version:31:raw",   "result": "SUCCESS" },
  { "actor": "steward@example.com", "action": "DELETE", "object": "dataset:12:version:32:clean", "result": "SUCCESS" },
  { "actor": "steward@example.com", "action": "EXPIRE", "object": "dataset:12",                  "result": "SUCCESS" },
  { "actor": "steward@example.com", "action": "EXPIRE", "object": "request:7",                   "result": "SUCCESS" }
]
```

Ініціатор видно в `actor`: для планувальника там `scheduler`, тож у журналі (UC-11) Steward відрізняє автоматичне видалення від дострокового.

## 6. UC-12: картка набору

### 6.1. Де Provider вводить опис і семантику

Окремим `PATCH`, **не** в тілі `POST /publish`. Тіло публікації лишається `{"retention_until": "YYYY-MM-DD"}`, щоб не ламати UI SCRUM-62. Опис і семантика не входять у ворота публікації (3.5): їх можна заповнити до або після публікації.

### `PATCH /api/datasets/{id}/metadata`

**Доступ**

| Без токена | Owner | Foreign | Consumer | Steward |
| --- | --- | --- | --- | --- |
| 401 | 200 | 404 | 403 | 403 |

**Тіло запиту** — обидва поля необов'язкові, передане поле замінює збережене значення повністю:

```json
{
  "description": "Виплати працівникам за 2026 р. для зовнішнього аудиту",
  "column_semantics": {
    "employee_id": "Табельний номер працівника",
    "full_name": "ПІБ працівника",
    "ipn": "Реєстраційний номер облікової картки платника податків",
    "amount_uah": "Сума виплати, грн"
  }
}
```

- `description: null` або `""` — очистити опис.
- `column_semantics` — повна заміна мапи (а не злиття). `{}` або `null` — очистити. UI надсилає всю мапу з форми.
- Ключ, якого немає в `Dataset.columns` → 422. Порожнє значення або довше 300 символів → 422.
- Опис і семантика — метадані, а не дані: редагувати можна і для `published` (рішення 2 ADR-002 стосується файлу очищеної версії). Для `expired` — 409.

**Відповідь 200**

```json
{
  "id": 12,
  "description": "Виплати працівникам за 2026 р. для зовнішнього аудиту",
  "column_semantics": {
    "employee_id": "Табельний номер працівника",
    "full_name": "ПІБ працівника",
    "ipn": "Реєстраційний номер облікової картки платника податків",
    "amount_uah": "Сума виплати, грн"
  }
}
```

**Коди відповідей**

| Код | Коли | `detail` |
| --- | --- | --- |
| 200 | Збережено | — |
| 403 | Consumer або Steward | `Access forbidden: only the dataset owner can edit metadata` |
| 404 | Неіснуючий або чужий набір | `Dataset not found.` |
| 409 | Набір `expired` | `Dataset is expired` |
| 422 | Невідома колонка, порожній або задовгий опис колонки, опис набору > 2000 | стандартна помилка валідації FastAPI або `Unknown column 'xyz'` |

**Аудит:** `UPDATE_METADATA`, `object=dataset:{id}`, `SUCCESS`. Відмови: 403 → `ACCESS_DENIED` / `FORBIDDEN`, 404 → `UPDATE_METADATA` / `FAILURE`, 409 → `UPDATE_METADATA` / `CONFLICT`. Текст опису в аудит не пишеться.

`GET /api/datasets` (список для Provider і Steward) додатково віддає `description`, `column_semantics`, `expired_at`, `expired_by` (поля в `DatasetResponse`), щоб форма редагування могла показати поточні значення.

### 6.2. Список каталогу

### `GET /api/catalog?q={рядок}&data_class={клас}`

**Доступ:** будь-яка автентифікована роль (як зараз), 401 без токена. Показуються **лише набори зі статусом `published`** для всіх ролей. Власні неопубліковані набори Provider бачить на сторінці «Набори» (`GET /api/datasets`, UC-12 AC1), а не в каталозі.

**Параметри запиту**

| Параметр | Тип | Обов'язковий | Поведінка |
| --- | --- | --- | --- |
| `q` | рядок, до 100 символів | ні | Пошук за назвою: підрядок без урахування регістру (`ILIKE '%q%'`), пробіли на краях обрізаються. Порожній — без фільтра. > 100 символів → 422 |
| `data_class` | `Internal` \| `Confidential` \| `Personal` | ні | Точний збіг класу. Інше значення → 422 |

Параметри комбінуються через AND. Сортування: `published_at` від нових до старих. Пагінації в MVP немає.

**Відповідь 200** — масив; нові поля позначено `// new`, наявні не змінюються (сумісність з UI SCRUM-63):

```json
[
  {
    "id": 12,
    "name": "payroll",
    "description": "Виплати працівникам за 2026 р. для зовнішнього аудиту",
    "data_class": "Personal",
    "row_count": 500,
    "quality_score": 91.8,
    "anonymization_methods": [
      { "column": "full_name", "method": "mask" },
      { "column": "ipn", "method": "hmac" },
      { "column": "iban", "method": "mask" }
    ],
    "uploaded_by": "provider@example.com",
    "created_at": "2026-11-20T09:15:00",
    "published_at": "2026-11-20T10:02:11",
    "retention_until": "2027-12-31",
    "legal_basis_status": "active"
  }
]
```

- `description` — `null`, якщо не заповнено. `// new`
- `published_at`, `retention_until` — з `Dataset`. `// new`
- `legal_basis_status` — зведений статус для бейджа в списку: `active` (є хоча б одна чинна підстава), `revoked` (є лише відкликані), `expired` (є лише прострочені, не відкликані), `none` (записів немає). Якщо є і відкликані, і прострочені, без чинних — `revoked`. `// new`
- `row_count` лишається кількістю рядків **сирого** набору (як зараз); кількість рядків очищеної версії — у картці (`versions`).

**Аудит:** успішний перегляд каталогу не пишеться (як зараз). 422 — стандартна валідація, без аудиту.

### 6.3. Картка одного набору

### `GET /api/catalog/{id}`

**Доступ**

| Стан набору | Без токена | Owner | Foreign | Consumer | Steward |
| --- | --- | --- | --- | --- | --- |
| `published` | 401 | 200 | 200 | 200 | 200 |
| `uploaded` | 401 | 200 | 404 | 404 | 200 |
| `expired` | 401 | 200 | 404 | 404 | 200 |
| не існує | 401 | 404 | 404 | 404 | 404 |

Опублікований набір у каталозі бачать усі ролі, тому Foreign отримує 200. Неопублікований чи видалений Consumer і Foreign не бачать: 404 (UC-12, EX1/EX2, рішення PO №8).

**Відповідь 200**

```json
{
  "id": 12,
  "name": "payroll",
  "description": "Виплати працівникам за 2026 р. для зовнішнього аудиту",
  "status": "published",
  "data_class": "Personal",
  "quality_score": 91.8,
  "row_count": 500,
  "file_type": "csv",
  "uploaded_by": "provider@example.com",
  "created_at": "2026-11-20T09:15:00",
  "published_at": "2026-11-20T10:02:11",
  "retention_until": "2027-12-31",
  "expired_at": null,
  "columns": [
    { "name": "employee_id",  "type": "object",  "semantics": "Табельний номер працівника", "method": null },
    { "name": "full_name",    "type": "string",  "semantics": "ПІБ працівника", "method": "mask" },
    { "name": "ipn",          "type": "string",  "semantics": "Реєстраційний номер облікової картки платника податків", "method": "hmac" },
    { "name": "iban",         "type": "string",  "semantics": null, "method": "mask" },
    { "name": "amount_uah",   "type": "float64", "semantics": "Сума виплати, грн", "method": null },
    { "name": "payment_date", "type": "object",  "semantics": null, "method": null }
  ],
  "legal_basis": [
    {
      "id": "6f1c2e9a-0b7d-4c55-9a51-3f7f3a1d2b10",
      "type": "contract",
      "purpose": "reporting",
      "date": "2026-11-01",
      "valid_until": "2027-12-31",
      "status": "active",
      "revoked_at": null
    }
  ],
  "versions": [
    { "kind": "raw",   "row_count": 500, "created_at": "2026-11-20T09:15:00" },
    { "kind": "clean", "row_count": 484, "created_at": "2026-11-20T09:40:27",
      "methods": [
        { "column": "full_name", "method": "mask" },
        { "column": "ipn", "method": "hmac" },
        { "column": "iban", "method": "mask" }
      ] }
  ],
  "anonymization_methods": [
    { "column": "full_name", "method": "mask" },
    { "column": "ipn", "method": "hmac" },
    { "column": "iban", "method": "mask" }
  ]
}
```

**Правила полів**

- `columns` — колонки **очищеної** версії в порядку з `Dataset.columns`.
  - `type` — тип з `Dataset.columns` (pandas dtype: `int64`, `float64`, `object`, …). Для колонок з методом `mask`, `hmac` або `generalize` — `string`, бо після обробки значення стають рядками (наприклад, `age` → `40-49`).
  - `semantics` — з `column_semantics`, `null`, якщо не заповнено.
  - `method` — метод анонімізації колонки або `null`.
- `legal_basis` — усі записи реєстру для набору, нові першими. Статус обчислюється так само, як у `legal_basis_service`: `revoked` (є `revoked_at`) → `expired` (`valid_until < today`) → `active`. **Без** `document_ref`, `revoked_reason`, `entered_by`: це договірні дані, які Consumer не потрібні (governance 3.3). Owner і Steward бачать повні записи через `GET /api/datasets/{id}/legal-basis`.
- `versions` — lineage «оригінал → очищена», від старої до нової:
  - Consumer і Foreign отримують **лише `clean`** (UC-12, AC3);
  - Owner і Steward — `raw` і `clean`;
  - без `file_path` і `sha256` для всіх ролей;
  - `row_count` у `clean` — після відкидання reject-рядків (ADR-002, рішення 1);
  - для `uploaded` без очищеної версії — лише `raw` (для Owner / Steward).
- `anonymization_methods` — те саме, що в списку (для сумісності; UI може брати методи з `columns`).
- `expired_at` — заповнене лише для `expired`. Для `expired`-набору `columns`, `legal_basis`, `versions` віддаються так само (метадані лишаються), але файлів немає.

**Коди відповідей**

| Код | Коли | `detail` |
| --- | --- | --- |
| 200 | Картку показано | — |
| 401 | Немає токена | як зараз |
| 404 | Не існує або недоступний за роллю (таблиця доступу) | `Dataset not found.` |

**Аудит:** успішний перегляд не пишеться (як для списку). 404 → `VIEW_CARD`, `object=dataset:{id}`, `FAILURE` (ADR-002, рішення 3: кожна відмова має слід).

## 7. Типи TypeScript для frontend

Рекомендовані типи для `frontend/src/api/types.ts`; назви полів збігаються з JSON вище.

```ts
export type DatasetStatus = 'uploaded' | 'published' | 'expired';
export type ExchangeRequestStatus = 'pending' | 'approved' | 'rejected' | 'downloaded' | 'expired';
export type DataClass = 'Internal' | 'Confidential' | 'Personal';
export type AnonymizationMethod = 'mask' | 'generalize' | 'hmac';
export type LegalBasisStatus = 'active' | 'revoked' | 'expired';

export interface CatalogItem {
  id: number;
  name: string;
  description: string | null;
  data_class: DataClass | null;
  row_count: number;
  quality_score: number | null;
  anonymization_methods: { column: string; method: AnonymizationMethod }[];
  uploaded_by: string;
  created_at: string;
  published_at: string | null;
  retention_until: string | null;
  legal_basis_status: LegalBasisStatus | 'none';
}

export interface DatasetCard {
  id: number;
  name: string;
  description: string | null;
  status: DatasetStatus;
  data_class: DataClass | null;
  quality_score: number | null;
  row_count: number;
  file_type: 'csv' | 'json';
  uploaded_by: string;
  created_at: string;
  published_at: string | null;
  retention_until: string | null;
  expired_at: string | null;
  columns: { name: string; type: string; semantics: string | null; method: AnonymizationMethod | null }[];
  legal_basis: {
    id: string;
    type: 'consent' | 'contract' | 'law';
    purpose: 'analytics' | 'research' | 'reporting' | 'publication';
    date: string;
    valid_until: string | null;
    status: LegalBasisStatus;
    revoked_at: string | null;
  }[];
  versions: {
    kind: 'raw' | 'clean';
    row_count: number;
    created_at: string;
    methods?: { column: string; method: AnonymizationMethod }[];
  }[];
  anonymization_methods: { column: string; method: AnonymizationMethod }[];
}

export interface DatasetMetadataUpdate {
  description?: string | null;
  column_semantics?: Record<string, string> | null;
}

export interface ExpireResult {
  dataset_id: number;
  status: 'expired';
  expired_at: string;
  expired_by: string;
  deleted_versions: { version_id: number; kind: 'raw' | 'clean' }[];
  expired_requests: number[];
}
```

**Що показує UI (орієнтир для SCRUM-84, 85, 86):**

- бейдж `expired` у списку наборів і в картці для Owner / Steward; у списку запитів — бейдж `expired` замість кнопок дій;
- кнопка «Видалити достроково» в картці лише для Steward і лише для `published`, з підтвердженням (дія незворотна);
- на 410 при завантаженні — повідомлення «Набір видалено після терміну зберігання», а не загальна помилка;
- для Consumer у картці — лише очищена версія, без `raw`.

## 8. Як перевірити (для SCRUM-81, 82 і SCRUM-89)

Мінімальний набір автотестів, який підтверджує контракт:

| Що | Очікування |
| --- | --- |
| `POST /expire` для кожної ролі | Матриця доступу з розділу 2; додати рядок у `RESOURCE_MATRIX` (`test_rbac_matrix.py`) |
| `run_retention` з `retention_until` у минулому | Файли видалено, набір і `pending`/`approved`/`downloaded` запити → `expired`, `rejected` без змін, події `DELETE` × 2 і `EXPIRE` з `actor=scheduler` |
| `run_retention` з `retention_until = today` | Набір не змінюється |
| Помилка видалення файлу (monkeypatch `os.remove`) | Статус `published`, `DELETE` / `FAILURE` |
| Файлів уже немає | Набір → `expired` без `DELETE` |
| Download для `expired` | 410, `DENY` / `request:{id}:expired` |
| `GET /api/catalog?q=PAY&data_class=Personal` | Лише опубліковані з назвою, що містить `pay`, класу `Personal` |
| `GET /api/catalog/{id}` для Consumer | Немає `raw` у `versions`, немає `document_ref` |
| `PATCH /metadata` з невідомою колонкою | 422 |

## 9. Історія змін контракту

| Версія | Дата | Що змінено | Повідомлено в задачах |
| --- | --- | --- | --- |
| 1.0 | 27.11.2026 | Перша версія | SCRUM-81, 82, 84, 85, 86 |
