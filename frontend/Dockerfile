# CodeInsight AI frontend image: builds the Vite production bundle, then
# serves it as static files via nginx (also proxying /api to the backend
# service so the browser never needs a separate backend hostname/port).
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
