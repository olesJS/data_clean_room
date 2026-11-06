# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

# Копіюємо весь вихідний код
COPY . .

# Видаляємо можливий Windows node_modules і встановлюємо заново під Linux
RUN rm -rf node_modules && npm ci --silent

# Збираємо production-бандл (VITE_API_URL порожній — nginx проксує /api → backend)
RUN VITE_API_URL="" VITE_USE_MOCK=false npm run build

# ── Stage 2: serve ─────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS serve

# Конфігурація nginx: роздаємо статику і проксуємо /api → backend:8000
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Копіюємо збілджений бандл
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
