# Data Clean Room — frontend

React + Vite + TypeScript. Каркас UI для Спринту 1: логін, навігація за роллю, захищені маршрути, форма завантаження файлу.

## Вимоги

- Node.js 18 або новіший (перевірка: `node -v`)

## Запуск

```bash
cd frontend
npm install
cp .env.example .env     # у Windows PowerShell: copy .env.example .env
npm run dev
```

Застосунок відкриється на http://localhost:5173.

## Команди

| Команда             | Що робить                                   |
| ------------------- | ------------------------------------------- |
| `npm run dev`       | Dev-сервер із гарячим перезавантаженням     |
| `npm run build`     | Перевірка типів і production-збірка в `dist/` |
| `npm run preview`   | Локальний перегляд збірки                   |
| `npm run lint`      | ESLint                                      |
| `npm run typecheck` | Лише перевірка типів TypeScript             |

## Змінні середовища (`.env`)

| Змінна              | Значення за замовчуванням | Призначення                                                         |
| ------------------- | ------------------------- | ------------------------------------------------------------------- |
| `VITE_API_URL`      | порожньо                  | Базова адреса API. Порожньо = той самий origin (у dev працює проксі) |
| `VITE_PROXY_TARGET` | `http://localhost:8000`   | Куди Vite проксіює запити `/api` у dev-режимі                       |
| `VITE_USE_MOCK`     | `true`                    | `true` = заглушка без бекенду, `false` = реальний API               |

Після зміни `.env` перезапусти `npm run dev`.

## Режим заглушки і перехід на реальний API

Поки бекенд не готовий, працює заглушка (`VITE_USE_MOCK=true`). Роль визначається за логіном:

| Логін містить | Роль         |
| ------------- | ------------ |
| `steward`     | DataSteward  |
| `consumer`    | DataConsumer |
| інше          | DataProvider |

Пароль може бути будь-яким непорожнім. Щоб побачити стани входу з UC-01:

- пароль `wrong` дає помилку «Невірний логін або пароль» (EX1);
- логін, що містить `locked` (наприклад, `locked@x.com`), дає тимчасове блокування (EX2).

Для переходу на реальний API постав `VITE_USE_MOCK=false` і перезапусти `npm run dev`.

## Контракт API

- `POST /api/auth/login` приймає `{ email, password }` і повертає `{ access_token, token_type, role }`. Невірний пароль дає 401 `{ detail }`. Поле «Логін» у формі надсилається як `email`: **підтвердити з C, що логін і є email**.
- Тимчасове блокування (UC-01, EX2) фронтенд розпізнає за статусом 423 або 429. **Узгодити з C, який код поверне API.**
- `GET /api/auth/me` із заголовком `Authorization: Bearer <token>` повертає `{ id, email, role }`. 401, якщо токен недійсний.
- `GET /api/datasets` повертає масив версій наборів. Припущена форма описана в `src/api/types.ts` (`DatasetVersion`). **Узгодити з D.**
- `POST /api/datasets` приймає `multipart/form-data` із полями `name`, `file` і необов’язковим `dataset_id` (нова версія існуючого набору). **Узгодити з D.**

Усі адреси зібрані в `src/config.ts` (`endpoints`).

## Ролі та навігація

| Роль         | Пункти меню                                          | Сторінки                          |
| ------------ | ---------------------------------------------------- | --------------------------------- |
| DataProvider | Мої набори даних, Імпортувати дані, Запити на доступ | `/datasets`, `/upload`, `/access` |
| DataConsumer | Каталог, Мої запити                                  | `/catalog`, `/requests`           |
| DataSteward  | Каталог (метадані), Журнал аудиту                    | `/catalog`, `/audit`              |

Пункти, недоступні ролі, не показуються. Прямий перехід на чужу сторінку показує «Немає доступу». Без токена будь-яка сторінка переспрямовує на `/login`. Відповідь 401 від API очищає токен і повертає на логін.

Токен і роль зберігаються в `localStorage` (достатньо для прототипу).

## Структура

```
src/
  api/          запити до API, типи, заглушка (mock.ts)
  auth/         AuthProvider, захист маршрутів, localStorage
  components/   Button, Field, Alert, Badges, QualityScore, Table, PageHeader, StubPage
  layout/       AppLayout (бічне меню) і правила навігації (nav.ts)
  pages/        екрани; Audit, Catalog, Requests, AccessRequests, Profile: заглушки
  styles/       tokens.css (токени з Figma) і global.css
```

## CORS

У dev це не потрібно (проксі Vite). Для production бекенд має дозволити origin фронтенду.
