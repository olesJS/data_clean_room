# Матриця RBAC і автотести (SCRUM-33, SCRUM-51)

Автотести: `backend/tests/test_rbac_matrix.py`. Запускаються в CI разом з рештою `pytest`. Очікування взято з матриці доступу (`docs/governance/data-governance-requirements.md`, розділ 3.2) та специфікацій UC.

## Частина 1. Ендпоінти без ресурсу в шляху

| Ендпоінт | Без токена | Data Provider | Data Consumer | Data Steward |
| --- | --- | --- | --- | --- |
| `GET /`, `GET /health`, `GET /health/db` | 200 | 200 | 200 | 200 |
| `GET /api/auth/me` | 401 | 200 | 200 | 200 |
| `POST /datasets`, `POST /api/datasets` | 401 | 201 | 403 | 403 |
| `GET /datasets`, `GET /api/datasets` | 401 | 200 (лише власні) | 200 (лише опубліковані) | 200 |
| `GET /audit`, `GET /api/audit` | 401 | 403 | 403 | 200 |

Дефект **SCRUM-52** (Consumer бачив неопубліковані набори) виправлено, `xfail` з тесту `test_consumer_does_not_see_unpublished_datasets` знято.

## Частина 2. Ендпоінти з ресурсом у шляху (SCRUM-51)

Тут п'ять ролей: окремо власник набору і чужий Data Provider. За рішенням PO №8 чужий ресурс і неіснуючий ресурс невідрізненні: обидва дають 404, щоб не можна було перебирати id.

| Ендпоінт | Без токена | Власник (Provider) | Чужий Provider | Consumer | Steward |
| --- | --- | --- | --- | --- | --- |
| `GET /api/datasets/{id}/profile` | 401 | 200 | 404 | 403 | 200 |
| `GET /api/datasets/{id}/pii` | 401 | 200 | 404 | 403 | 200 |
| `PATCH /api/datasets/{id}/pii/{column}` | 401 | 200 | 404 | 403 | 403 |
| `GET /api/datasets/{id}/quality-rules` | 401 | 200 | 404 | 403 | 200 |
| `GET /api/datasets/{id}/quality-violations` | 401 | 200 | 404 | 403 | 200 |
| `POST /api/datasets/{id}/legal-basis` | 401 | 201 | 404 | 403 | 201 |
| `GET /api/datasets/{id}/legal-basis` | 401 | 200 | 404 | 403 | 200 |
| `POST /api/legal-basis/{id}/revoke` | 401 | 200 | 404 | 403 | 200 |
| `POST /api/datasets/{id}/anonymize/preview` | 401 | 200 | 404 | 403 | 403 |
| `POST /api/datasets/{id}/anonymize` | 401 | 200 | 404 | 403 | 403 |
| `GET /api/datasets/{id}/publish/check` | 401 | 200 | 404 | 403 | 403 |
| `POST /api/datasets/{id}/publish` | 401 | 200 | 404 | 403 | 403 |
| `GET /api/catalog` | 401 | 200 | 200 | 200 | 200 |
| `POST /api/requests` | 401 | 403 | 403 | 201 | 403 |
| `GET /api/requests` | 401 | 200 (на свої набори) | 200 (на свої набори) | 200 (власні) | 200 (усі) |
| `POST /api/requests/{id}/approve` | 401 | 200 | 404 | 403 | 403 |
| `POST /api/requests/{id}/reject` | 401 | 200 | 404 | 403 | 403 |
| `GET /api/requests/{id}/download` | 401 | 404 | 404 | 200 (автор запиту) | 404 |

Примітки:

- Запит розглядає власник набору, а не Steward (UC-09, рішення PO). Steward отримує 403.
- Завантажити файл може лише автор запиту. Для решти ролей запит «не існує» (404), щоб не розкривати чужі запити.
- Старі шляхи без `/api` (`/datasets/{id}/profile`, `/datasets/{id}/legal-basis`, `/legal-basis/{id}/revoke` тощо) ведуть у ті самі обробники, тому окремо не тестуються.
- Для кожного кейсу фікстура `world` створює свіжі ресурси: набір-чернетку, готовий до публікації (чиста версія і методи для всіх PII-колонок), два опубліковані набори, активну підставу з метою `analytics`, запит у статусі `pending` і запит у статусі `approved`. Тому змінювальні виклики (публікація, відкликання, рішення) не впливають на інші кейси.

## Що перевіряють тести

| Тест | Що перевіряє | Кейсів |
| --- | --- | --- |
| `test_rbac_matrix` | Частина 1: кожна роль на кожному ендпоінті отримує код з матриці | 40 |
| `test_denied_request_is_audited` | Частина 1: кожна відмова 401 і 403 додає рівно один запис в аудит (`UNAUTHORIZED_ACCESS`/`UNAUTHORIZED` або `ACCESS_DENIED`/`FORBIDDEN`, actor, шлях) | 15 |
| `test_denied_upload_creates_no_dataset` | Відхилене завантаження не створює набір | 6 |
| `test_invalid_token_is_rejected_and_audited` | Підроблений, прострочений, без `sub`, неіснуючого користувача токен дає 401 і запис в аудит | 28 |
| `test_role_claim_in_token_does_not_grant_access` | Роль береться з БД: поле `role` у токені не дає прав Steward | 1 |
| `test_provider_sees_only_own_datasets` | Provider бачить у списку лише власні набори | 1 |
| `test_consumer_does_not_see_unpublished_datasets` | Consumer не бачить неопублікованих наборів (SCRUM-52) | 1 |
| `test_resource_rbac_matrix` | Частина 2: п'ять ролей × 18 ендпоінтів | 90 |
| `test_resource_denial_is_audited` | Частина 2: кожна відмова 401 і 403 додає рівно один запис з цим actor і `result` `UNAUTHORIZED` або `FORBIDDEN` | 43 |
| `test_denied_publish_does_not_publish` | Відмова в публікації не змінює статус набору | 3 |
| `test_denied_review_keeps_request_pending` | Відмова в рішенні залишає запит у `pending` без рецензента | 6 |
| `test_denied_revoke_keeps_basis_active` | Відмова у відкликанні залишає підставу активною | 2 |

У частині 2 назва дії в аудиті різниться між роутерами (`ACCESS_DENIED`, `GET_DATASET_PII`, `CREATE_LEGAL_BASIS`, `REVOKE_LEGAL_BASIS` тощо), тому тест перевіряє спільний інваріант: actor і результат.

## Помічено під час розширення матриці

- Відповідь 404 на `approve`/`reject` для чужого або неіснуючого запиту не пишеться в аудит. Решта роутерів пишуть 404 як `FAILURE`. Тестом не закріплено, винесено на обговорення з PO.
- Негативні сценарії обміну (дублікат запиту, коротка мета, рішення без підстави, повторне рішення, завантаження без схвалення) — у `backend/tests/test_exchange_negative.py` (SCRUM-68).

## Як додати новий ендпоінт

- Ендпоінт без ресурсу в шляху: рядок у `MATRIX` з кодами для чотирьох ролей. Тести відмов, аудиту й невалідних токенів підхоплять його автоматично.
- Ендпоінт з ресурсом: рядок у `RESOURCE_MATRIX` з кодами для п'яти ролей (`_codes(anon, owner, other, consumer, steward)`). Плейсхолдер у шляху (`{draft}`, `{published}`, `{spare}`, `{basis}`, `{pending}`, `{approved}`) підставляється з фікстури `world`. Якщо потрібен ресурс в іншому стані, його додають у `world`.
