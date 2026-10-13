import { appeler, NonConnecte } from "./api";

export type Etat = "unknown" | "online" | "offline";

/** Pourquoi une Caméra est dans son état, quand ArgOS le sait. */
export type RaisonEtat = "autre_appareil";

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
  raison_etat: RaisonEtat | null;
  /** MAC de l'Appareil (`aa:bb:cc:dd:ee:ff`), lue sur le réseau ; `null` : inconnue. */
  mac: string | null;
  /** Nom d'encodage lu dans le SDP (`H264`, `H265`, `MJPEG`…) ; `null` : jamais lu. */
  codec: string | null;
  /** Chemin MediaMTX qui relaie le Flux (`camera-<id>`) ; `null` si la Caméra est désactivée. */
  chemin_flux: string | null;
};

export type SaisieCamera = { nom: string; url_rtsp: string; emplacement: string | null };

/** MAC à afficher ; « — » si inconnue (réseau routé, Caméra d'avant la 0.4.2). */
export function texteMac(mac: string | null): string {
  return mac ?? "—";
}

const CODECS: Record<string, string> = { H264: "H.264", H265: "H.265" };

/** Codec à afficher : « H.264 », « H.265 », « inconnu » si jamais lu, tout autre tel quel. */
export function texteCodec(codec: string | null): string {
  return codec === null ? "inconnu" : (CODECS[codec] ?? codec);
}

const RAISONS_ETAT: Record<RaisonEtat, string> = {
  autre_appareil: "autre appareil à cette adresse",
};

/** Pourquoi la Caméra est dans cet état, à afficher à côté ; `null` si ArgOS ne le sait pas. */
export function texteRaison(raison: RaisonEtat | null): string | null {
  return raison === null ? null : RAISONS_ETAT[raison];
}

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

/** L'URL masquée renvoyée telle quelle désigne l'URL stockée : le mot de passe RTSP est conservé. */
export async function modifierCamera(id: number, modification: Partial<SaisieCamera & { active: boolean }>): Promise<void> {
  await envoyer(`/api/cameras/${id}`, "PATCH", modification);
}

/** Seule une Caméra désactivée peut être supprimée. */
export async function supprimerCamera(id: number): Promise<void> {
  await envoyer(`/api/cameras/${id}`, "DELETE");
}
