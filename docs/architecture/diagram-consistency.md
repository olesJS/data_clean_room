# Перевірка узгодженості діаграм — SCRUM-59

Дата: 12.11.2026

Обсяг: `sequence-exchange.puml`, `sequence-publish.puml`, `class-diagram.puml`.

## Рішення PO (12.11.2026)

1. **Хто схвалює запит:** лише власник набору (`DataProvider`). Це відповідає UC-09 (EX1: не власник → 403). `DataSteward` не схвалює запити; описи Jira SCRUM-56/63/64/67/68 треба виправити окремо.
2. **Статуси запиту:** `Requested → Approved | Rejected → Downloaded`; `Expired` — за `access_until` (UC-09 EX3, UC-10).
3. **Події аудиту:** `REQUEST` (створення), `REQUEST_APPROVED` / `REQUEST_REJECTED` (рішення), `DOWNLOAD`; відмова через підставу — `DENY` з `legal_basis_invalid`. Це відповідає UC-09/UC-10; governance 3.4 треба доповнити `REQUEST_APPROVED`/`REQUEST_REJECTED` разом із SCRUM-58.
4. **Публікація:** `GET /publish/check` — лише читання; анонімізація розділена на `POST /anonymize/preview` (без запису) і `POST /anonymize` (створює clean `DatasetVersion`). `POST /publish` виконує ворота.
5. **Правова підстава на публікації:** перевіряється будь-яка чинна підстава без `purpose`; `purpose` перевіряється на запиті Consumer. Рішення зафіксовано в governance 3.5.
6. **ExchangeRequest:** `consumer_id` / `reviewed_by` — назви SCRUM-56; `dataset_version_id` і `revoke()` прибрано; `access_until` / `Expired` залишено за UC-09 EX3.

## Матриця звірки

| Перевірка | Джерело істини | Статус | Примітки |
|---|---|---|---|
| Кроки exchange flow і гілки відмов | UC-08–UC-10, SCRUM-64 (Activity), SCRUM-56 | OK / TODO | Activity-діаграм SCRUM-64 ще немає в `main`; контракт узгодити з Назаром (SCRUM-56). |
| Роль approve/reject | UC-09 | OK | Лише `DataProvider`-власник; `DataSteward` не схвалює; Jira-описи 56/63/64/67/68 виправити окремо. |
| Статуси запиту | UC-09 / UC-10 | OK | `Requested` → `Approved` / `Rejected` → `Downloaded`; `Expired` за `access_until`. |
| Причини воріт публікації | raw-критерії SCRUM-57 | OK | `no_clean_version`, `pii_not_processed`, `hmac_without_legal_basis`, `retention_required`. |
| Причини відмови через згоду | SCRUM-58 | OK | `no_legal_basis`, `revoked`, `expired`, `purpose_mismatch`. |
| Назви подій аудиту | UC-09 / UC-10 + governance 3.4 | OK / Чернетка | `REQUEST`, `REQUEST_APPROVED`, `REQUEST_REJECTED`, `DOWNLOAD`, `DENY`; governance 3.4 доповнити разом із SCRUM-58. |
| Поля класів і кратності | `backend/app/models.py` + міграції SCRUM-55/57/58 | Чернетка | `DatasetVersion`, поля публікації та згоди — цільовий стан Спринту 3; перевірити після merge. |
| Назви ендпоінтів | raw-критерії SCRUM-57 | OK | `POST /api/datasets/{id}/anonymize/preview`, `POST /api/datasets/{id}/anonymize`, `GET /api/datasets/{id}/publish/check?retention_until=YYYY-MM-DD`, `POST /api/datasets/{id}/publish`, `POST /api/legal-basis/{id}/revoke`. |
| `GET /publish/check` не змінює стан | REST + SCRUM-55/57 | OK | Лише читання; `retention_until` передається параметром, бо до публікації поле набору ще порожнє; створення clean-версії — окремий `POST /anonymize`. |
| Місце exchange flow у проєкті | SCRUM-56 (Назар, backend) | OK | Flow не видалено; `sequence-exchange.puml` — контракт для SCRUM-56, а не дублювання реалізації. |
