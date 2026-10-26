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
 * Hôte qui répond en RTSP sur un port caméra. `camera` : Caméra du Site (active ou désactivée) du même Appareil
 * (MAC), sinon à la même IP et au même port, sinon `null`. `statut_rtsp` et `serveur` servent au diagnostic,
 * l'UI ne les montre pas. `mac` : celle de l'Appareil, `null` si illisible.
 * Appareil connu vu à une autre IP : `adresse_mise_a_jour` si la Détection a suivi ses Caméras, `conflit` si
 * une autre Caméra occupait déjà la nouvelle URL (Caméra non modifiée).
 */
export type Candidat = Adresse & {
  statut_rtsp: number;
  serveur: string | null;
  mac: string | null;
  camera: { id: number; nom: string } | null;
  adresse_mise_a_jour: { ancienne: string; nouvelle: string } | null;
  conflit: { id: number; nom: string } | null;
};

export type ResultatDetection = {
  sous_reseaux: string[];
  ports: number[];
  duree_s: number;
  /** Triés par IP puis port. */
  candidats: Candidat[];
};

/** Chiffres d'une MAC, comme l'API la normalise : séparateurs `:` `-` `.` et espaces retirés, en minuscules. */
function chiffresMac(mac: string): string {
  return mac.replaceAll(/[\s:.-]/g, "").toLowerCase();
}

/** Saisie du filtre que l'API refuserait aussi : autre chose que des chiffres hexadécimaux, ou plus de douze. */
export function filtreMacInvalide(saisie: string): boolean {
  return !/^[0-9a-f]{0,12}$/.test(chiffresMac(saisie));
}

/** `filtre` apparaît dans `chiffres` en commençant ou finissant entre deux octets : « ab » ne trouve pas `0a:b0`. */
function contientSurUnOctet(chiffres: string, filtre: string): boolean {
  for (let debut = chiffres.indexOf(filtre); debut !== -1; debut = chiffres.indexOf(filtre, debut + 1)) {
    if (debut % 2 === 0 || (debut + filtre.length) % 2 === 0) return true;
  }
  return false;
}

/**
 * Candidats dont la MAC contient `saisie`, tapée telle qu'écrite sur l'étiquette (`AA-BB-…`, `aabb.ccdd.eeff`,
 * partielle, alignée sur les octets). Saisie vide : tous ; invalide : aucun ; sinon, ceux sans MAC sont écartés.
 */
export function filtrerParMac(candidats: Candidat[], saisie: string): Candidat[] {
  const filtre = chiffresMac(saisie);
  if (filtre === "") return candidats;
  if (filtreMacInvalide(saisie)) return [];
  return candidats.filter((candidat) => candidat.mac !== null && contientSurUnOctet(chiffresMac(candidat.mac), filtre));
}

async function lire<T>(reponse: Response): Promise<T> {
  if (reponse.ok) return reponse.json();
  const corps = (await reponse.json().catch(() => ({}))) as { detail?: unknown };
  throw new Refus(
    typeof corps.detail === "string" ? corps.detail : `Refusé par l'API (${reponse.status}).`,
    reponse.status,
  );
}

export async function lireEtatDetection(): Promise<EtatDetection> {
  return lire(await appeler("/api/detection"));
}

/** Attente entre deux demandes quand une Détection tourne déjà, et nombre de demandes (une minute en tout). */
const ATTENTE_DETECTION_MS = 2_000;
const DEMANDES_DETECTION = 30;

/**
 * Détection synchrone : une dizaine de secondes pour un /24 sur deux ports. À n'appeler que Détection configurée :
 * un refus `409` dit alors qu'une autre tourne déjà (autre onglet, page rechargée pendant la sienne), et la
 * demande est refaite jusqu'à ce qu'elle se termine.
 */
export async function lancerDetection(): Promise<ResultatDetection> {
  for (let demande = 1; ; demande++) {
    try {
      return await lire(await appeler("/api/detection", { method: "POST" }));
    } catch (e) {
      if (!(e instanceof Refus && e.statut === 409) || demande >= DEMANDES_DETECTION) throw e;
      await new Promise((reprise) => setTimeout(reprise, ATTENTE_DETECTION_MS));
    }
  }
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
  /** MAC de l'Appareil dès qu'il a répondu ; `null` si injoignable ou illisible. */
  mac: string | null;
  /** Autre Caméra du même Appareil (même MAC, autre chemin) : avertissement, l'ajout reste permis. */
  appareil_deja_connu: { id: number; nom: string } | null;
  expiration_s: number;
};

/** Portés par l'URL de la Caméra ajoutée, côté serveur ; l'API ne les renvoie jamais. */
export type Identifiants = { identifiant: string; mot_de_passe: string };

/** Chemin RTSP saisi quand aucun chemin courant ne répond : seul ce chemin est essayé. */
export type DemandeEssai = Partial<Identifiants> & { chemin?: string };

/**
 * Cherche le Flux d'un Candidat ; remplace l'essai précédent et son Aperçu. Adresse d'une Caméra du Site (sauf
 * si un autre Appareil l'a reprise) ou Flux déjà configuré sur le même Appareil : refus « Déjà configurée : <nom> »,
 * sans Aperçu.
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
