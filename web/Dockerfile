# Étape 1 : build Vite (Node épinglé).
FROM node:24.21.0-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
# Aucun paquet n'a besoin de scripts d'installation sous Linux (fsevents ne sert que sur macOS).
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

# Étape 2 : fichiers statiques seulement, pas de proxy /api (le front appelle l'API sur son port).
# Image non privilégiée : nginx tourne en utilisateur nginx (pas root), d'où le port 8080 dans le conteneur.
FROM nginxinc/nginx-unprivileged:1.31.6-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
