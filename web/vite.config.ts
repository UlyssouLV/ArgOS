import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { Agent } from "node:https";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type ProxyOptions, type UserConfig } from "vite";

// Racine du dépôt : compose.yaml et .env.
const RACINE = "..";

// Build et dev : Tailwind (docs/adr/0016-tailwind-et-shadcn-ui-pour-l-ui-du-site.md), alias @/ → src/.
const COMMUN: UserConfig = {
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
};

// docker cherché dans ces dossiers seulement, pas dans le PATH : Docker Desktop, Homebrew, paquets Linux.
const DOCKERS = [
  "/usr/local/bin/docker",
  "/opt/homebrew/bin/docker",
  "/usr/bin/docker",
  "/Applications/Docker.app/Contents/Resources/bin/docker",
];

function docker(): string {
  const trouve = DOCKERS.find((chemin) => existsSync(chemin));
  if (!trouve) {
    throw new Error(`docker introuvable dans ${DOCKERS.join(", ")}`);
  }
  return trouve;
}

/** Fichier du volume certificats-serveur, lu par le service certificats, qui l'écrit. */
function lireCertificat(fichier: string): string {
  return execFileSync(
    docker(),
    ["compose", "run", "--rm", "--no-deps", "-T", "--entrypoint", "cat", "certificats", `/certificats-serveur/${fichier}`],
    // Sortie d'erreur de docker compose gardée pour le message d'échec, pas affichée sinon.
    { cwd: RACINE, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
  );
}

/** Premier certificat d'un fichier PEM : celui du Site, sans la chaîne qui peut le suivre. */
function premierCertificat(pem: string): string {
  const fin = "-----END CERTIFICATE-----";
  return pem.slice(0, pem.indexOf(fin) + fin.length);
}

// Dev : https://localhost:5173, avec le certificat serveur d'ArgOS, sous une seule origine comme en prod
// (docs/adr/0005-https-par-une-origine-unique-et-une-autorite-du-site.md) : /api et /flux sont relayés
// vers l'origine HTTPS de la stack lancée (docker compose up). Le certificat qu'elle présente doit être
// celui du Site, comparé tel quel comme dans api (soi.py) : juste aussi avec un certificat fourni par
// l'Administrateur, qui n'a pas d'Autorité du Site (pas d'argos-ca.crt) et ne nomme pas forcément localhost.
export default defineConfig(({ command, mode }) => {
  if (command !== "serve") {
    return COMMUN;
  }
  const portHttps = loadEnv(mode, RACINE, "ARGOS_").ARGOS_PORT_HTTPS || "443";
  const certificat = lireCertificat("serveur.crt");
  const relais: ProxyOptions = {
    target: `https://localhost:${portHttps}`,
    changeOrigin: true,
    agent: new Agent({
      // Seul certificat de confiance : celui du Site, donc aucun autre, et son nom ne compte plus.
      ca: premierCertificat(certificat),
      allowPartialTrustChain: true,
      checkServerIdentity: () => undefined,
    }),
  };
  return {
    ...COMMUN,
    server: {
      port: 5173,
      strictPort: true,
      host: true,
      https: { cert: certificat, key: lireCertificat("serveur.key") },
      proxy: { "/api": relais, "/flux": relais },
    },
  };
});
