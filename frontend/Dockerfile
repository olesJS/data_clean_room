# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS build

WORKDIR /app

# Копіюємо залежності окремо — кешування шару при незмінному package.json
COPY package.json package-lock.json ./
RUN npm ci --silent

# Копіюємо вихідний код і збираємо production-бандл
COPY . .
# VITE_API_URL залишаємо порожнім — nginx проксує /api на backend
RUN VITE_API_URL="" npm run build

# ── Stage 2: serve ─────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine AS serve

# Конфігурація nginx: роздаємо статику і проксуємо /api → backend:8000
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Копіюємо збілджений бандл
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
