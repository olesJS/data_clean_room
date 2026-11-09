# Перевірка узгодженості діаграм — SCRUM-59

Дата: 10.11.2026

Обсяг: `sequence-exchange.puml`, `sequence-publish.puml`, `class-diagram.puml`.

| Перевірка | Джерело істини | Статус | Примітки |
|---|---|---|---|
| Кроки exchange flow і гілки відмов | UC-06 / UC-07, SCRUM-64 (Activity), SCRUM-56 | TODO | Activity-діаграм SCRUM-64 ще немає в `main`. Контракт узгодити з Назаром (SCRUM-56). |
| Причини воріт публікації | raw-критерії SCRUM-57 | OK | `no_clean_version`, `pii_not_processed`, `hmac_without_legal_basis`, `retention_required`. |
| Причини відмови через згоду | raw-критерії SCRUM-57/58 | OK | `no_legal_basis`, `revoked`, `expired`, `purpose_mismatch`. |
| Назви подій аудиту | `docs/governance/data-governance-requirements.md`, розділ 3.4 | Чернетка | `PUBLISH` і `DENY` уже є; `CONSENT_REVOKED` і `DENY` з `legal_basis_invalid` додає SCRUM-57. |
| Поля класів і кратності | `backend/app/models.py` + міграції SCRUM-54/55/57 | Чернетка | `DatasetVersion` і нові поля публікації/згоди — цільовий стан Спринту 3; перевірити після merge міграцій. |
| Назви ендпоінтів | raw-критерії SCRUM-57 | OK | `GET /api/datasets/{id}/publish/check`, `POST /api/datasets/{id}/publish`, `POST /api/legal-basis/{id}/revoke`. |
| Місце exchange flow у проєкті | SCRUM-56 (Назар, D) | OK | Flow не видалено; `sequence-exchange.puml` — контракт для SCRUM-56, а не дублювання реалізації. |
