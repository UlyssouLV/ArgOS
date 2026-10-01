import { appeler, NonConnecte } from "./api";

export type Etat = "unknown" | "online" | "offline";

/** Représentation d'une Caméra par l'API : le mot de passe RTSP y est masqué (`***`). */
export type Camera = {
  id: number;
  nom: string;
  url_rtsp: string;
  emplacement: string | null;
  hote: string;
  port: number;
  active: boolean;
  etat: Etat;
  etat_verifie_le: string | null;
  /** Chemin MediaMTX qui relaie le Flux (`camera-<id>`) ; `null` si la Caméra est désactivée. */
  chemin_flux: string | null;
};

export type SaisieCamera = { nom: string; url_rtsp: string; emplacement: string | null };

/** Refus de l'API, à afficher tel quel dans le formulaire. */
export class Refus extends Error {}

const URL_INVALIDE = "URL RTSP invalide. Format attendu : rtsp://[utilisateur:motdepasse@]hote[:port]/chemin";

/** Message à montrer pour un échec d'appel ; `null` si la session est fermée (la connexion s'affiche). */
export function messageEchec(erreur: unknown): string | null {
  if (erreur instanceof NonConnecte) return null;
  if (erreur instanceof Refus) return erreur.message;
  return "L'API du Site ne répond pas. Réessayez dans un instant.";
}

async function lever(reponse: Response): Promise<never> {
  if (reponse.status === 422) throw new Refus(URL_INVALIDE);
  const corps = (await reponse.json().catch(() => ({}))) as { detail?: unknown };
  throw new Refus(typeof corps.detail === "string" ? corps.detail : `Refusé par l'API (${reponse.status}).`);
}

async function envoyer(chemin: string, methode: string, corps?: object): Promise<Response> {
  const reponse = await appeler(chemin, {
    method: methode,
    body: corps === undefined ? undefined : JSON.stringify(corps),
  });
  return reponse.ok ? reponse : lever(reponse);
}

export async function listerCameras(): Promise<Camera[]> {
  return (await envoyer("/api/cameras", "GET")).json();
}

export async function creerCamera(saisie: SaisieCamera): Promise<void> {
  await envoyer("/api/cameras", "POST", saisie);
}

/** L'URL masquée renvoyée telle quelle désigne l'URL stockée : le mot de passe RTSP est conservé. */
export async function modifierCamera(id: number, modification: Partial<SaisieCamera & { active: boolean }>): Promise<void> {
  await envoyer(`/api/cameras/${id}`, "PATCH", modification);
}

/** Seule une Caméra désactivée peut être supprimée. */
export async function supprimerCamera(id: number): Promise<void> {
  await envoyer(`/api/cameras/${id}`, "DELETE");
}
