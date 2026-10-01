// L'API est sur le même hôte que la page (localhost ou IP du réseau local), sur son propre port :
// le même build marche quelle que soit l'adresse ouverte dans le navigateur.
const PORT_API = import.meta.env.VITE_ARGOS_PORT_API || "8000";
export const URL_API = `${window.location.protocol}//${window.location.hostname}:${PORT_API}`;

/** Session absente, expirée ou révoquée : l'API a répondu 401. */
export class NonConnecte extends Error {}

let quandNonConnecte = () => {};

/** Appelé à chaque 401 d'une route protégée, pour renvoyer l'Administrateur sur la connexion. */
export function surNonConnecte(rappel: () => void): void {
  quandNonConnecte = rappel;
}

export function requete(chemin: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${URL_API}${chemin}`, {
    ...init,
    credentials: "include", // le cookie de session passe d'une origine à l'autre (CORS avec credentials)
    headers: init.body === undefined ? init.headers : { "Content-Type": "application/json", ...init.headers },
  });
}

/** Requête sur une route protégée : tout 401 ferme la session côté UI. */
export async function appeler(chemin: string, init: RequestInit = {}): Promise<Response> {
  const reponse = await requete(chemin, init);
  if (reponse.status === 401) {
    quandNonConnecte();
    throw new NonConnecte();
  }
  return reponse;
}
