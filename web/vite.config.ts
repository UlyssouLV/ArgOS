import { execFileSync } from "node:child_process";
import { Agent } from "node:https";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type ProxyOptions } from "vite";

// Racine du dépôt : compose.yaml et .env.
const RACINE = "..";

/** Fichier du volume certificats-serveur, lu par le service certificats, qui l'écrit. */
function lireCertificat(fichier: string): string {
  return execFileSync(
    "docker",
    ["compose", "run", "--rm", "--no-deps", "-T", "--entrypoint", "cat", "certificats", `/certificats-serveur/${fichier}`],
    // Sortie d'erreur de docker compose gardée pour le message d'échec, pas affichée sinon.
    { cwd: RACINE, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
  );
}

// Dev : https://localhost:5173, avec le certificat serveur d'ArgOS, sous une seule origine comme en prod
// (docs/adr/0005-https-par-une-origine-unique-et-une-autorite-du-site.md) : /api et /flux sont relayés
// vers l'origine HTTPS de la stack lancée (docker compose up), dont le certificat est vérifié contre l'Autorité.
export default defineConfig(({ command, mode }) => {
  if (command !== "serve") {
    return { plugins: [react()] };
  }
  const portHttps = loadEnv(mode, RACINE, "ARGOS_").ARGOS_PORT_HTTPS || "443";
  const relais: ProxyOptions = {
    target: `https://localhost:${portHttps}`,
    changeOrigin: true,
    agent: new Agent({ ca: lireCertificat("argos-ca.crt") }),
  };
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      host: true,
      https: { cert: lireCertificat("serveur.crt"), key: lireCertificat("serveur.key") },
      proxy: { "/api": relais, "/flux": relais },
    },
  };
});
