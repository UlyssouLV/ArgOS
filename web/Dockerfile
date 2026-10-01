# Étape 1 : build Vite (Node épinglé).
FROM node:24.21.0-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Étape 2 : fichiers statiques seulement, pas de proxy /api (le front appelle l'API sur son port).
FROM nginx:1.31.6-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
