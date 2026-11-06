# PR #13–#15: що виправлено, чому так і як закомітити

> **Статус:** це робочий документ. Я **не робив комітів і пушів**.
>
> **HITL:** спочатку переглянь `git diff` / `git diff --cached`, потім запускай команди коміту.
>
> **Головний порядок:** спочатку PR **#13 → #14 → #15** на pre-review. PR #18 поки не чіпаємо.
>
> **Цей `.md` не додається в PR**, якщо ти сам цього не захочеш. Не використовуй `git add .`.

---

## 0. Короткий підсумок

| PR | Що виправлено | Перевірка | Що ще не закрито |
|---|---|---|---|
| **#13** Class diagram | PlantUML generics, видалено `DatasetVersion`, профіль/PII як JSON, `QualityRule.dataset_id`, оновлено PNG | PlantUML `-checkonly` → 0; PNG після повторного рендеру має той самий SHA256; 1244×2155 | Одна помилка кратності `User — Dataset`; кілька полів `ColumnProfile` не з фактичної схеми PR #18 |
| **#14** Quality Engine | Score до 1 знака, missing column → 400, прибрано дублікати ключів, ліміт `violating_indices`, `pyyaml`, тести на реальних даних | `ruff` чисто; **44 passed**; payroll = 91.8, customers = 87.0 | Інтеграція `validate_dataframe` у PR #18 — окремим кроком |
| **#15** Legal Basis | RBAC до БД, Consumer → 403, sync-сесія, моделі в `app/models.py`, audit у тій самій сесії, 6 тестів | `ruff` чисто; **40 passed** | Alembic досі не налаштований; async-двигун і `aiosqlite` не прибрані; зайвий index у міграції |

**Важливо:** зелені CI на GitHub зараз відносяться до **старих HEAD-комітів**, а не до цих незакомічених виправлень. Після пушу CI треба дочекатися.

---

## 1. Де що лежить

```text
main worktree (PR #15):
C:\Users\dmytr\data_clean_room

PR #13 worktree:
C:\Users\dmytr\AppData\Local\Temp\opencode\dcr-pr13

PR #14 worktree:
C:\Users\dmytr\AppData\Local\Temp\opencode\dcr-pr14

venv:
C:\Users\dmytr\data_clean_room\backend\.venv\Scripts
```

Поточні гілки/HEAD:

| PR | Гілка | HEAD зараз |
|---|---|---|
| #13 | `feature/SCRUM-39-class-diagram` | `f8b4a49` |
| #14 | `feature/SCRUM-40-quality-engine` | `89e3346` |
| #15 | `feature/SCRUM-50-legal-basis` | `d542f2b` |

Рев’юери, яких можна додати після пушу: `olesJS`, `samura1h`, `shybivska`, `sonuax`.
`olesJS` уже робив `CHANGES_REQUESTED` на всі три PR — після виправлень його варто перезапросити.

---

## 2. PR #13 — Class Diagram

### 2.1. Що виправлено після review

1. **PlantUML generics**
   - Було: `list~ColumnProfile~`, `list~PiiFinding~`.
   - Стало: `List<ColumnProfile>`, `List<PiiFinding>`.
   - PNG перегенеровано.

2. **Прибрано `DatasetVersion`**
   - У PR #18 немає окремої таблиці версій.
   - `ColumnProfile` і `PiiFinding` — це **JSON-структури** в `Dataset.profile_json` / `Dataset.pii_json`, а не окремі таблиці.
   - На діаграмі вони позначені `<<JSON>>`; додано note, що це embedded JSON.

3. **`QualityRule` / `RuleViolation`**
   - Замість `dataset_version_id` тепер `dataset_id`.
   - Правила й порушення прив’язані до dataset, а не до неіснуючої версії.

4. **Основні поля звірені з поточним кодом/рев’ю**
   - `ColumnProfile`: `outliers_count`, `min`, `max`, `mean`, `null_percentage` тощо.
   - `PiiFinding`: `user_confirmed`, `corrected_pii_type`, `detection_method`.
   - `AnonymizationMethod`: `dataset_id`, `pii_finding_ref`.
   - `LegalBasis.id`: UUID (у БД — `String(36)`).
   - `duplicate_count` / `future_dates_count` — planned-поля, яких немає в PR #18 (див. 2.3).

### 2.2. Архітектурне рішення — для тебе

**Діаграма тепер описує “as-built” стан Sprint 2, а не ідеальну цільову модель.**

Чому так:

- `DatasetVersion` прибрано, бо в поточному коді його немає. Малювати таблицю, якої не існує, — гірше, ніж чесно показати JSON-кеш.
- `profile_json` / `pii_json` — прагматичне рішення: профіль колонок і PII-знахідки мають різну вкладену структуру, їх простіше зберігати як JSON, ніж одразу нормалізувати в окремі таблиці.
- **Trade-off:** JSON не дає FK-цілісності та SQL-запитів по окремих PII-полях. Якщо в Sprint 3 з’явиться потреба в аналітиці/lineage, тоді робимо окремі `column_profiles` / `pii_findings` і міграцію даних.
- `Role` як окрему таблицю прибрано, бо в коді `User.role` — рядок. Це відповідає фактичній реалізації. Якщо хочете нормалізований RBAC (`roles`, `role_id`), це окреме архітектурне рішення, а не просто правка діаграми.
- `QualityRule` на `dataset_id` — правила застосовуються до набору, а не до версії. Якщо пізніше з’явиться версіонування, це рішення треба переглянути.

### 2.3. Що ще варто виправити перед комітом

Це не блокери review, але я помітив:

1. Кратність:

   ```text
   User "*" --- "1" Dataset : owns >
   ```

   Логічно має бути:

   ```text
   User "1" --- "0..*" Dataset : owns >
   ```

   Один користувач може володіти багатьма наборами; у набору один власник.

2. `ColumnProfile` містить `duplicate_count` і `future_dates_count`, яких зараз немає в `ColumnProfile` з PR #18. Або прибери їх, або познач як “planned fields”, щоб не було розбіжності з назвою “aligned with PR #18 schema”.

### 2.4. Текст для PR description

```md
### Оновлення після review

- PlantUML generics приведені до `List<ColumnProfile>` / `List<PiiFinding>`; PNG перегенеровано.
- Діаграму приведено до фактичної схеми Sprint 2: `DatasetVersion` прибрано, `ColumnProfile` і `PiiFinding` показані як JSON-структури в `Dataset.profile_json` / `Dataset.pii_json`.
- `QualityRule` і `RuleViolation` прив’язані до `dataset_id`, а не до `dataset_version_id`.
- `duplicate_count` / `future_dates_count` залишені як planned-поля; якщо потрібен строгий as-built, їх можна прибрати (див. 2.3).
- `LegalBasis.id` показаний як UUID (`String(36)` у БД), `AnonymizationMethod` — через `dataset_id` + `pii_finding_ref`.

### Архітектурне рішення

Діаграма описує поточний стан реалізації, а не майбутню нормалізовану модель. JSON-зберігання профілю/PII — свідомий компроміс Sprint 2: простіше і швидше, але без FK та SQL-аналітики по окремих полях. Нормалізація — окреме рішення для наступного етапу.

### Перевірка

- PlantUML `-checkonly` — успішно.
- PNG повторно відрендерено; SHA256 збігається з файлом у PR.
```

### 2.5. Команди для PR #13

```powershell
$wt13 = "C:\Users\dmytr\AppData\Local\Temp\opencode\dcr-pr13"

# 1. Перегляд
git -C $wt13 status --short
git -C $wt13 diff --check
git -C $wt13 diff --stat
git -C $wt13 diff -- docs/architecture/class-diagram.puml

# 2. Перевірка PlantUML (jar уже є в temp)
java -jar C:\Users\dmytr\AppData\Local\Temp\opencode\plantuml.jar `
  -checkonly $wt13\docs\architecture\class-diagram.puml

# 3. Коміт ТІЛЬКИ після перегляду
git -C $wt13 add docs/architecture/class-diagram.puml docs/architecture/class-diagram.png
git -C $wt13 diff --cached --stat
git -C $wt13 commit -m "docs(architecture): align class diagram with sprint-2 schema"

# 4. Перегляд САМОГО коміту (HITL-ворота)
git -C $wt13 --no-pager show --stat --oneline HEAD
git -C $wt13 --no-pager show --color=never HEAD -- docs/architecture/class-diagram.puml

# 5. Пуш і pre-review — ТІЛЬКИ після перегляду коміту
git -C $wt13 push origin feature/SCRUM-39-class-diagram
gh pr edit 13 --repo olesJS/data_clean_room `
  --add-reviewer olesJS,samura1h,shybivska,sonuax
```

---

## 3. PR #14 — Quality Engine

### 3.1. Що виправлено після review

1. **Score округлюється до 1 знака**
   - Було `round(..., 2)`.
   - Стало `round(..., 1)`.
   - Тест на дублікати: `66.67` → `66.7`.

2. **Відсутня колонка — це помилка конфігурації, а не “якість 0”**
   - Було: rule для неіснуючої колонки давав violation на всі рядки / score 0.
   - Стало: `YAMLRuleParsingError` зі `status_code=400`, у detail перелічені доступні колонки.
   - Це fail-fast: краще не публікувати dataset, ніж порахувати неправдивий score.

3. **Прибрано дублікати ключів у відповіді**
   - Було: `Score` + `score`, `violation_count` + `total_violations`.
   - Стало: канонічні `Score` і `violation_count`.

4. **Обмежено `violating_indices`**
   - Максимум 100 індексів на правило.
   - `violation_count` залишається повним.
   - Додано `violating_indices_truncated: true/false`.

5. **`pyyaml` додано явно**
   - `pyyaml>=6.0` у `backend/requirements.txt`.
   - Не покладаємось на транзитивну залежність від `uvicorn[standard]`.

6. **Тести на реальних даних**
   - `data/payroll.csv` з `dtype={"ipn": str}` — щоб не загубити провідні нулі ІПН.
   - `data/payroll_rules.yaml` → Score **91.8**, 500 рядків, 10 дублікатів.
   - `data/customers.json` + `data/customers_rules.yaml` → Score **87.0**, 1000 рядків, 15 дублікатів.
   - Перевіряються і per-rule counts: `ipn=15`, `amount_uah=8`, `payment_date=8`, `city=40` тощо.

### 3.2. Архітектурне рішення — для тебе

- **`N_пр` — це union рядків**, а не сума violations. Рядок, який порушив 3 правила, рахується один раз. Це робить Score стабільним і не залежить від кількості правил.
- **`reject` / `flag` зменшують Score, `block` — ні.**
  - `block` — це policy-заборона публікації (`can_publish=False`, `has_blocking_violations=True`).
  - Якість даних і право на публікацію — різні речі; тому `block` не псує метрику.
- **Missing column → 400.** Це не дефект даних, а розсинхрон YAML і DataFrame. Якщо тихо поставити 0, можна випадково заблокувати/опублікувати не те.
- **Обмеження `violating_indices`** — захист API від величезних відповідей. Повна кількість є в `violation_count`.
- **Канонічні ключі** — щоб frontend/PR #18 не залежав від двох різних назв одного поля.
- **YAML як зовнішні правила** — правила можна змінювати без зміни коду; engine лишається чистою функцією `DataFrame + rules → result`.

### 3.3. Що ще не входить у PR #14

Це важливо для інтеграції:

- PR #18 досі рахує Quality Score власною формулою в `profiler.py` (`rows_with_null + duplicate_rows_count`), а не через `validate_dataframe`.
- Після merge PR #14 у PR #18 треба замінити цю ad-hoc формулу на виклик `validate_dataframe` і передавати `data/*_rules.yaml`.
- Це окремий commit у PR #18, не в PR #14.

### 3.4. Текст для PR description

```md
### Оновлення після review

- Score округлюється до одного знака після коми.
- Відсутня в DataFrame колонка, на яку посилається YAML-правило, тепер дає `YAMLRuleParsingError` з HTTP 400 і списком доступних колонок, а не “Score = 0”.
- Прибрано дублікати ключів відповіді: залишено канонічні `Score` і `violation_count`.
- `violating_indices` обмежено 100 записами; повна кількість — у `violation_count`, факт обрізання — у `violating_indices_truncated`.
- `pyyaml>=6.0` додано явно.
- Додано регресійні тести на реальних `data/payroll.csv` і `data/customers.json`: 91.8 та 87.0, з перевіркою per-rule counts.

### Архітектурне рішення

`N_пр` — це унікальні рядки з `reject`/`flag`-порушеннями плюс дублікати, об’єднані через union. `block` не зменшує Score, а лише забороняє публікацію. Відсутня колонка — це помилка конфігурації, тому fail-fast 400.

### Перевірка

- `ruff check .` — чисто.
- `pytest` — 44 passed.
- Реальні дані: payroll 91.8, customers 87.0.
```

### 3.5. Команди для PR #14

```powershell
$wt14 = "C:\Users\dmytr\AppData\Local\Temp\opencode\dcr-pr14"
$venv = "C:\Users\dmytr\data_clean_room\backend\.venv\Scripts"

# 1. Перегляд
git -C $wt14 status --short
git -C $wt14 diff --check
git -C $wt14 diff --stat
git -C $wt14 diff -- backend/app/services/quality_engine.py

# 2. Перевірка
Push-Location "$wt14\backend"
& "$venv\ruff.exe" check .
$env:DATABASE_URL = "sqlite:///:memory:"
$env:ENV = "test"
& "$venv\python.exe" -m pytest -o addopts="-ra" --disable-warnings -q
Remove-Item Env:DATABASE_URL
Remove-Item Env:ENV
Pop-Location

# 3. Коміт ТІЛЬКИ після перегляду
git -C $wt14 add backend/app/services/quality_engine.py backend/requirements.txt backend/tests/test_quality_engine.py
git -C $wt14 diff --cached --stat
git -C $wt14 commit -m "fix(quality): align score contract and add real-data regression tests"

# 4. Перегляд САМОГО коміту (HITL-ворота)
git -C $wt14 --no-pager show --stat --oneline HEAD
git -C $wt14 --no-pager show --color=never HEAD

# 5. Пуш і pre-review — ТІЛЬКИ після перегляду коміту
git -C $wt14 push origin feature/SCRUM-40-quality-engine
gh pr edit 14 --repo olesJS/data_clean_room `
  --add-reviewer olesJS,samura1h,shybivska,sonuax
```

---

## 4. PR #15 — Legal Basis Registry

### 4.1. Що виправлено після review

1. **RBAC перевіряється до будь-якого запиту до БД**
   - Consumer не може навіть дізнатися, чи існує dataset.
   - `POST` для Consumer на неіснуючий dataset → **403**, а не 404.
   - `GET` для Consumer → **403**.

2. **Правило власності**
   - `DataProvider` — тільки власний dataset.
   - `DataSteward` — будь-який dataset.
   - `DataConsumer` — заборонено.

3. **Синхронний роутер**
   - Замість `AsyncSession` / `get_async_db` — звичайний `Session` / `get_db`.
   - Це прибирає подвійний engine/session і проблеми з двома in-memory SQLite БД у тестах.

4. **Моделі централізовано**
   - `LegalBasis` і `LegalBasisType` перенесені в `backend/app/models.py`.
   - Старий пакет `backend/models/` видалено.
   - Більше немає `from models.legal_basis import ...` та `noqa: E402`.

5. **Audit у тій самій сесії**
   - `log_event(..., db=db)` для success/forbidden/not-found.
   - Записи аудиту й зміни йдуть через одну сесію/БД; тести їх бачать.

6. **Тести**
   - Успішне створення/читання.
   - Steward може створювати.
   - Provider не може керувати чужим dataset.
   - Consumer не може читати.
   - Consumer POST на неіснуючий dataset → 403 (перевірка “RBAC до БД”).
   - Dataset not found → 404 для Provider.
   - Всього **40 passed**, `ruff` чисто.

### 4.2. Архітектурне рішення — для тебе

- **Одна sync-сесія на запит.** Проєкт і решта роутерів уже використовують `get_db`; додавати async тільки для legal basis було дорого:
  - два двигуни;
  - окремі session factories;
  - у тестах — окремі in-memory SQLite;
  - складніше гарантувати, що audit і зміна бачать один стан.
- Якщо колись переходити на async — це робиться **глобально** для всього застосунку, а не окремим роутером.
- **RBAC до БД** — це не лише “правильний код відповіді”. Це захист від enumeration: по 404 не можна зрозуміти, чи dataset існує.
- **`entered_by` береться з JWT**, а не з payload. Клієнт не може підробити авторство.
- **UUID генерується на сервері**; у БД зберігається `String(36)`.
- **Модель в `app/models.py`** — щоб був один `Base.metadata` і один import path. Старий `backend/models/` був shim’ом і створював плутанину.

### 4.3. Що ще не закрито (це важливо)

Ці пункти з review **ще не входять у поточний worktree-коміт**:

1. **Alembic реально не налаштований.**
   - Є тільки `backend/alembic/versions/001_create_legal_basis_table.py`.
   - Немає `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`.
   - `init_db()` досі викликає `Base.metadata.create_all`.
   - Тобто файл міграції “мертвий”, поки немає конфігурації.
   - Це блокер review #15; треба або налаштувати Alembic повністю, або узгодити з викладачем інший варіант.

2. **Async-двигун і `aiosqlite` залишились.**
   - У `backend/app/database.py` ще є `create_async_engine`, `AsyncSessionLocal`, `get_async_db`.
   - У `requirements.txt` ще є `aiosqlite>=0.20.0`.
   - Після переходу роутера на sync це вже не використовується; прибрати окремим cleanup-комітом.

3. **Зайвий index `ix_legal_basis_id`.**
   - У моделі `id` вже primary key, окремий index не потрібен.
   - В Alembic-міграції він ще створюється; прибрати.

4. **`create_all` vs Alembic.**
   - Поки `create_all` лишається, production-схема не керується міграціями.
   - Це треба вирішити до merge, а не після.

### 4.4. Текст для PR description

```md
### Оновлення після review

- RBAC перевіряється до звернення до БД: Consumer отримує 403 навіть для неіснуючого dataset, а не 404.
- DataProvider керує лише власними наборами; DataSteward — будь-якими; DataConsumer — заборонено.
- Роутер переведений на sync `Session` / `get_db`; прибрано окремий async-шлях для legal basis.
- `LegalBasis` і `LegalBasisType` перенесені в `app/models.py`; старий пакет `backend/models/` видалено.
- Audit-записи пишуться в тій самій сесії (`db=db`).
- Додано 6 тестів на RBAC/ownership/not-found; всього 40 passed.

### Архітектурне рішення

Одна sync-сесія на запит відповідає решті застосунку й прибирає дублювання engine/session. RBAC до БД захищає від enumeration dataset’ів. `entered_by` і UUID генеруються на сервері, а не приймаються від клієнта.

### Наступним кроком

- Повністю налаштувати Alembic (`alembic.ini`, `env.py`) і прибрати `create_all`.
- Прибрати невикористаний async engine та `aiosqlite`.
- Прибрати зайвий `ix_legal_basis_id` з міграції.
```

### 4.5. Команди для PR #15

```powershell
$repo = "C:\Users\dmytr\data_clean_room"
$venv = "$repo\backend\.venv\Scripts"

# 0. Прибрати випадковий 0-байтний артефакт (не комітити)
Remove-Item "$repo\backend\file" -ErrorAction SilentlyContinue

# 1. Перегляд
git -C $repo status --short
git -C $repo diff --check
git -C $repo diff --stat
git -C $repo diff -- backend/app/models.py backend/app/routers/legal_basis.py

# 2. Перевірка
Push-Location "$repo\backend"
& "$venv\ruff.exe" check .
$env:DATABASE_URL = "sqlite:///:memory:"
$env:ENV = "test"
& "$venv\python.exe" -m pytest -o addopts="-ra" --disable-warnings -q
Remove-Item Env:DATABASE_URL
Remove-Item Env:ENV
Pop-Location

# 3. Коміт ТІЛЬКИ після перегляду.
#    Явно додаємо і видалення старого пакета.
git -C $repo add `
  backend/app/models.py `
  backend/app/routers/legal_basis.py `
  backend/models/__init__.py `
  backend/models/legal_basis.py `
  backend/tests/test_legal_basis.py

git -C $repo diff --cached --stat
git -C $repo diff --cached --name-status
git -C $repo commit -m "fix(legal-basis): enforce RBAC before lookup and use sync session"

# 4. Перегляд САМОГО коміту (HITL-ворота)
git -C $repo --no-pager show --stat --oneline HEAD
git -C $repo --no-pager show --color=never HEAD

# 5. Пуш і pre-review — ТІЛЬКИ після перегляду коміту
git -C $repo push origin feature/SCRUM-50-legal-basis
gh pr edit 15 --repo olesJS/data_clean_room `
  --add-reviewer olesJS,samura1h,shybivska,sonuax
```

> `docs/scrum/sprint-2-pr-description.md` — окреме рішення. Не додавай його випадково в PR #15.

---

## 5. Порядок pre-review

1. **PR #13** — найменший і найбезпечніший; після нього рев’юери бачать актуальну діаграму.
2. **PR #14** — quality engine; після нього можна посилатися на `validate_dataframe` у PR #18.
3. **PR #15** — legal basis; після нього закриваються RBAC-зауваження.
4. **Тільки потім PR #18** — інакше він змішує свої проблеми з вашими.

Після кожного пушу:

```powershell
gh pr view 13 --repo olesJS/data_clean_room --json url,state,reviewDecision
gh pr view 14 --repo olesJS/data_clean_room --json url,state,reviewDecision
gh pr view 15 --repo olesJS/data_clean_room --json url,state,reviewDecision
```

Отримати посилання одним списком:

```powershell
13,14,15 | ForEach-Object {
  gh pr view $_ --repo olesJS/data_clean_room --json url --jq .url
}
```

Перевірити, що PR оновився на новий HEAD, і дочекатися CI:

```powershell
gh pr view 13 --repo olesJS/data_clean_room --json url,headRefOid,reviewDecision
gh pr view 14 --repo olesJS/data_clean_room --json url,headRefOid,reviewDecision
gh pr view 15 --repo olesJS/data_clean_room --json url,headRefOid,reviewDecision

gh pr checks 13 --repo olesJS/data_clean_room --watch
gh pr checks 14 --repo olesJS/data_clean_room --watch
gh pr checks 15 --repo olesJS/data_clean_room --watch
```

### 5.1. Повідомлення, яке можна кинути друзям

```text
Привіт! Оновив свої PR після review, прошу pre-review:

#13 — Class diagram (as-built схема Sprint 2):
https://github.com/olesJS/data_clean_room/pull/13

#14 — Quality Engine (score, YAML rules, real-data tests):
https://github.com/olesJS/data_clean_room/pull/14

#15 — Legal Basis (RBAC до БД, sync session, 6 тестів):
https://github.com/olesJS/data_clean_room/pull/15

PR #18 поки не чіпаємо — спочатку закриваємо ці три PR.
```

---

## 6. Докази перевірок

| Перевірка | Результат |
|---|---|
| PR #13: PlantUML `-checkonly` | exit 0 |
| PR #13: повторний рендер PNG | SHA256 збігається; 244548 bytes; 1244×2155 |
| PR #14: `ruff check .` | All checks passed |
| PR #14: `pytest` | **44 passed**, 2 warnings in 8.05s (exit 0) |
| PR #14: payroll | Score 91.8, 500 rows, 10 duplicates |
| PR #14: customers | Score 87.0, 1000 rows, 15 duplicates |
| PR #15: `ruff check .` | All checks passed |
| PR #15: `pytest` | **40 passed**, 2 warnings in 9.33s (exit 0) |
| PR #15: legal basis tests | 6 tests |
| `gh auth status` | logged in as `dmyrkoo` |

> Це результати **локальних worktree**, а не GitHub CI. CI на GitHub перевіряв старі HEAD-коміти; після пушу буде новий run.

---

## 7. Чого не робити

- Не запускати `git add .` — у PR #15 є `backend/file` і `docs/scrum/...`, які не входять у цей коміт.
- Не комітити цей `.md` у PR #13–#15.
- Не видаляти worktree `dcr-pr13` / `dcr-pr14`, поки зміни не закомічені.
- Не змішувати PR #13–#15 з PR #18.
- Не пушити, поки не переглянув `git diff --cached`.

---

## 8. Що я НЕ робив

- Не виконував `git add`, `git commit`, `git push`.
- Не створював і не змінював коміти в PR #13–#15.
- Не публікував review у PR #18.
- Не додавав цей файл у Git.
