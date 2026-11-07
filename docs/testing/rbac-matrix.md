# Матриця RBAC і автотести (SCRUM-33)

Автотести: `backend/tests/test_rbac_matrix.py`. Запускаються в CI разом з рештою `pytest`. Очікування взято з матриці доступу (`docs/governance/data-governance-requirements.md`, розділ 3.2) та специфікацій UC.

## Матриця «ендпоінт × роль → код відповіді»

| Ендпоінт | Без токена | Data Provider | Data Consumer | Data Steward |
| --- | --- | --- | --- | --- |
| `GET /`, `GET /health`, `GET /health/db` | 200 | 200 | 200 | 200 |
| `GET /api/auth/me` | 401 | 200 | 200 | 200 |
| `POST /datasets`, `POST /api/datasets` | 401 | 201 | 403 | 403 |
| `GET /datasets`, `GET /api/datasets` | 401 | 200 (лише власні) | 200 ⚠ | 200 |
| `GET /audit`, `GET /api/audit` | 401 | 403 | 403 | 200 |

⚠ Відомий дефект **SCRUM-52**: Data Consumer отримує в списку всі завантажені (неопубліковані) набори. За матрицею 3.2 сирий набір Consumer заборонено, решта доступна лише Public або після схвалення запиту. Тест `test_consumer_does_not_see_unpublished_datasets` позначено `xfail(strict=True)`: після виправлення він почне проходити, і `xfail` треба буде зняти в межах SCRUM-52.

## Що перевіряють тести

| Тест | Що перевіряє | Кейсів |
| --- | --- | --- |
| `test_rbac_matrix` | Кожна роль на кожному ендпоінті отримує код з матриці | 40 |
| `test_denied_request_is_audited` | Кожна відмова 401 і 403 додає рівно один запис в аудит (`UNAUTHORIZED_ACCESS`/`UNAUTHORIZED` або `ACCESS_DENIED`/`FORBIDDEN`, actor, шлях) | 15 |
| `test_denied_upload_creates_no_dataset` | Відхилене завантаження не створює набір | 6 |
| `test_invalid_token_is_rejected_and_audited` | Підроблений, прострочений, без `sub`, неіснуючого користувача токен дає 401 і запис в аудит | 28 |
| `test_role_claim_in_token_does_not_grant_access` | Роль береться з БД: поле `role` у токені не дає прав Steward | 1 |
| `test_provider_sees_only_own_datasets` | Provider бачить у списку лише власні набори | 1 |
| `test_consumer_does_not_see_unpublished_datasets` | Відомий дефект (xfail) | 1 |

## Як додати новий ендпоінт

Додати рядок у словник `MATRIX` у `test_rbac_matrix.py` з кодами для чотирьох ролей. Тести відмов, аудиту й невалідних токенів підхоплять його автоматично. Обсяг цього документа: ендпоінти, які є в `main`. Ендпоінти PR #15 (правова підстава) і PR #18 (профіль, PII, PATCH PII, видалення набору) додаються після їх злиття в задачі **SCRUM-51**.
