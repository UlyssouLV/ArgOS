import { appeler } from "./api";
import { Refus } from "./cameras";

/** Position d'une Incrustation ; `Custom` : hors d'un coin, placée par la caméra. */
export type Position = "UpperLeft" | "UpperRight" | "LowerLeft" | "LowerRight" | "Custom";

export type Horloge = {
  date_heure_utc: string;
  /** Écart avec l'heure du Site, en secondes ; positif : la caméra avance. */
  ecart_s: number;
  fuseau_posix: string | null;
  /** Nom IANA (`Europe/Paris`) si ArgOS reconnaît le fuseau POSIX. */
  fuseau: string | null;
  mode: "manuel" | "ntp";
  serveur_ntp: string | null;
};

export type IncrustationNom = {
  affichee: boolean;
  texte: string | null;
  position: Position | null;
  peut_etre_reaffichee: boolean;
};

export type IncrustationDateHeure = {
  affichee: boolean;
  format: string | null;
  position: Position | null;
  peut_etre_reaffichee: boolean;
};

/** Réglages de la Caméra, lus sur la caméra par ONVIF à chaque ouverture. */
export type Reglages = {
  horloge: Horloge;
  incrustations: { nom: IncrustationNom; date_heure: IncrustationDateHeure };
};

export type CodeErreurOnvif = "sans_onvif" | "identifiants_refuses" | "injoignable";

const MESSAGES_ONVIF: Record<CodeErreurOnvif, string> = {
  sans_onvif: "Cette caméra ne répond pas en ONVIF.",
  identifiants_refuses: "La caméra refuse ces identifiants en ONVIF.",
  injoignable: "Caméra injoignable.",
};

/** `502` de l'API : la caméra n'a pas pu être lue par ONVIF. */
export class ErreurOnvif extends Refus {}

export async function lireReglages(idCamera: number): Promise<Reglages> {
  const reponse = await appeler(`/api/cameras/${idCamera}/reglages`);
  if (reponse.ok) return reponse.json();
  const corps = (await reponse.json().catch(() => ({}))) as { code?: CodeErreurOnvif; detail?: unknown };
  if (reponse.status === 502 && corps.code && corps.code in MESSAGES_ONVIF) {
    throw new ErreurOnvif(MESSAGES_ONVIF[corps.code]);
  }
  throw new Refus(typeof corps.detail === "string" ? corps.detail : `Refusé par l'API (${reponse.status}).`);
}

const POSITIONS: Record<Position, string> = {
  UpperLeft: "en haut à gauche",
  UpperRight: "en haut à droite",
  LowerLeft: "en bas à gauche",
  LowerRight: "en bas à droite",
  Custom: "position personnalisée",
};

export function textePosition(position: Position | null): string {
  return position === null ? "—" : POSITIONS[position];
}

const UNITES: [number, string, string][] = [
  [365.25 * 24 * 3600, "an", "ans"],
  [24 * 3600, "jour", "jours"],
  [3600, "h", "h"],
  [60, "min", "min"],
  [1, "s", "s"],
];

/** « en retard de 26 ans », « en avance de 3 min » ; « à l'heure » à moins d'une seconde près. */
export function texteEcart(ecartS: number): string {
  const absolu = Math.abs(ecartS);
  const unite = UNITES.find(([duree]) => absolu >= duree);
  if (!unite) return "à l'heure";
  const [duree, singulier, pluriel] = unite;
  const nombre = Math.floor(absolu / duree);
  return `${ecartS < 0 ? "en retard" : "en avance"} de ${nombre} ${nombre > 1 ? pluriel : singulier}`;
}

/** Fuseau lisible s'il est reconnu, sinon la chaîne POSIX de la caméra telle quelle. */
export function texteFuseau(horloge: Horloge): string {
  return horloge.fuseau ?? horloge.fuseau_posix ?? "—";
}

/** Date et heure UTC de la caméra, au format français. */
export function texteDateHeure(dateHeureUtc: string): string {
  return new Date(dateHeureUtc).toLocaleString("fr-FR", { timeZone: "UTC" });
}
