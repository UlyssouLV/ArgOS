// L'API est servie sous /api par la même origine HTTPS que la page (docs/adr/0005-…) : chemins relatifs,
// le même build marche quelle que soit l'adresse ouverte dans le navigateur.

/** Session absente, expirée ou révoquée : l'API a répondu 401. */
export class NonConnecte extends Error {}

let quandNonConnecte = () => {};

/** Appelé à chaque 401 d'une route protégée, pour renvoyer l'Administrateur sur la connexion. */
export function surNonConnecte(rappel: () => void): void {
  quandNonConnecte = rappel;
}

export function requete(chemin: string, init: RequestInit = {}): Promise<Response> {
  return fetch(chemin, {
    ...init,
    headers: init.body === undefined ? init.headers : { "Content-Type": "application/json", ...init.headers },
  });
}

/** Requête sur une route protégée (API ou Flux WHEP) : tout 401 ferme la session côté UI. */
export async function appeler(chemin: string, init: RequestInit = {}): Promise<Response> {
  const reponse = await requete(chemin, init);
  if (reponse.status === 401) {
    signalerNonConnecte();
    throw new NonConnecte();
  }
  return reponse;
}

/** Un 401 reçu hors d'`appeler` (requêtes HLS, faites par hls.js) : ferme la session côté UI. */
export function signalerNonConnecte(): void {
  quandNonConnecte();
}

/** Faux si l'API refuse la session (et l'UI revient alors à la connexion) ; vrai sinon, même si l'API ne répond pas. */
export async function sessionValide(): Promise<boolean> {
  try {
    await appeler("/api/session");
    return true;
  } catch (erreur) {
    return !(erreur instanceof NonConnecte);
  }
}
