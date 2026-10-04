import { appeler } from "./api";
import { Refus, type Camera } from "./cameras";

/** Réglage de la Détection : `raison` dit pourquoi elle est indisponible (`null` : configurée). */
export type EtatDetection = {
  configuree: boolean;
  sous_reseaux: string[];
  ports: number[];
  raison: string | null;
};

/** Hôte et port RTSP d'un appareil : Candidat détecté, ou IP saisie à la main. */
export type Adresse = { ip: string; port: number };

/**
 * Hôte qui répond en RTSP sur un port caméra. `camera` : Caméra du Site (active ou désactivée) à la même
 * IP et au même port, sinon `null`. `statut_rtsp` et `serveur` servent au diagnostic, l'UI ne les montre pas.
 */
export type Candidat = Adresse & {
  statut_rtsp: number;
  serveur: string | null;
  camera: { id: number; nom: string } | null;
};

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

/** Issue d'un essai : seul `flux_trouve` ouvre un Aperçu. */
export type Issue = "flux_trouve" | "identifiants_requis" | "identifiants_refuses" | "flux_introuvable" | "injoignable";

/**
 * Résultat d'un essai ; `apercu` : chemin MediaMTX à lire en WebRTC, seulement si `flux_trouve`.
 * Sans renouvellement pendant `expiration_s`, l'API retire l'Aperçu.
 */
export type Essai = {
  issue: Issue;
  chemin: string | null;
  codec: string | null;
  apercu: string | null;
  expiration_s: number;
};

/** Portés par l'URL de la Caméra ajoutée, côté serveur ; l'API ne les renvoie jamais. */
export type Identifiants = { identifiant: string; mot_de_passe: string };

/** Chemin RTSP saisi quand aucun chemin courant ne répond : seul ce chemin est essayé. */
export type DemandeEssai = Partial<Identifiants> & { chemin?: string };

/**
 * Cherche le Flux d'un Candidat ; remplace l'essai précédent et son Aperçu. Adresse d'une Caméra du Site :
 * refus « Déjà configurée : <nom> », sans essai.
 */
export async function essayer(ip: string, port: number, demande: DemandeEssai = {}): Promise<Essai> {
  return lire(await appeler("/api/essai", { method: "POST", body: JSON.stringify({ ip, port, ...demande }) }));
}

/** Prolonge l'Aperçu de l'essai ; `false` s'il a déjà été retiré (expiré ou remplacé). */
export async function renouvelerEssai(): Promise<boolean> {
  const reponse = await appeler("/api/essai/renouveler", { method: "POST" });
  if (reponse.status === 404) return false;
  if (!reponse.ok) await lire(reponse);
  return true;
}

/** Retire l'essai en cours et son Aperçu (sans erreur s'il n'y en a pas). */
export async function retirerEssai(): Promise<void> {
  const reponse = await appeler("/api/essai", { method: "DELETE" });
  if (!reponse.ok) await lire(reponse);
}

/** Crée une Caméra active à partir du Flux de l'essai, côté serveur ; un nom pris laisse l'essai ouvert. */
export async function ajouterDepuisEssai(nom: string, emplacement: string | null): Promise<Camera> {
  return lire(await appeler("/api/essai/camera", { method: "POST", body: JSON.stringify({ nom, emplacement }) }));
}
