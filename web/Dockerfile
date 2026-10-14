# Étape 1 : build Vite (Node épinglé).
FROM node:24.21.0-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
# Aucun paquet n'a besoin de scripts d'installation sous Linux (fsevents ne sert que sur macOS).
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

# Étape 2 : l'origine HTTPS du Site (nginx.conf.template) : fichiers statiques, relais de l'API et du Live.
# Image non privilégiée : nginx tourne en utilisateur nginx (pas root) ; Docker lui ouvre les ports < 1024.
FROM nginxinc/nginx-unprivileged:1.31.6-alpine
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 443 8080
