import { appeler } from "./api";
import { Refus } from "./cameras";

/** Réglage de la Détection : `raison` dit pourquoi elle est indisponible (`null` : configurée). */
export type EtatDetection = {
  configuree: boolean;
  sous_reseaux: string[];
  ports: number[];
  raison: string | null;
};

/** Hôte qui répond en RTSP sur un port caméra, et n'est pas (encore) une Caméra du Site. */
export type Candidat = { ip: string; port: number };

export type ResultatDetection = {
  sous_reseaux: string[];
  ports: number[];
  duree_s: number;
  /** Triés par IP puis port. */
  candidats: Candidat[];
};

async function lire<T>(reponse: Response): Promise<T> {
  if (reponse.ok) return reponse.json();
  const corps = (await reponse.json().catch(() => ({}))) as { detail?: unknown };
  throw new Refus(typeof corps.detail === "string" ? corps.detail : `Refusé par l'API (${reponse.status}).`);
}

export async function lireEtatDetection(): Promise<EtatDetection> {
  return lire(await appeler("/api/detection"));
}

/** Détection synchrone : une dizaine de secondes pour un /24 sur deux ports. */
export async function lancerDetection(): Promise<ResultatDetection> {
  return lire(await appeler("/api/detection", { method: "POST" }));
}
