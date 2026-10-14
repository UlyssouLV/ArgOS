import { appeler } from "./api";
import { Refus } from "./cameras";

export type Coin = "UpperLeft" | "UpperRight" | "LowerLeft" | "LowerRight";
/** Position d'une Incrustation ; `Custom` : hors d'un coin, placée par la caméra. */
export type Position = Coin | "Custom";
export const COINS: Coin[] = ["UpperLeft", "UpperRight", "LowerLeft", "LowerRight"];

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
  return lever(reponse);
}

/** Envoie une fois l'heure du Site à la caméra (mode manuel, fuseau gardé) ; rend son Horloge relue. */
export async function mettreALHeure(idCamera: number): Promise<Horloge> {
  const reponse = await appeler(`/api/cameras/${idCamera}/reglages/mise-a-l-heure`, { method: "POST" });
  if (reponse.ok) return reponse.json();
  return lever(reponse);
}

/** Envoie seulement les champs modifiés ; l'API relit la caméra et dit, pour chacun, s'il a été pris. */
export async function modifierReglages(idCamera: number, modification: Modification): Promise<ResultatModification> {
  const reponse = await appeler(`/api/cameras/${idCamera}/reglages`, {
    method: "PATCH",
    body: JSON.stringify(modification),
  });
  if (reponse.ok) return reponse.json();
  return lever(reponse);
}

async function lever(reponse: Response): Promise<never> {
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

/**
 * Fuseaux proposés, Europe/Paris en tête : ceux que l'API reconnaît à la lecture (`FUSEAUX_COURANTS`,
 * api/argos_api/fuseaux.py), pour qu'un fuseau choisi ici soit relu sous le même nom.
 */
export const FUSEAUX = [
  "Europe/Paris",
  "UTC",
  "Europe/London",
  "Europe/Lisbon",
  "Europe/Athens",
  "Europe/Moscow",
  "Africa/Casablanca",
  "Africa/Abidjan",
  "America/Guadeloupe",
  "America/Cayenne",
  "America/Miquelon",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Indian/Reunion",
  "Indian/Mayotte",
  "Asia/Dubai",
  "Asia/Shanghai",
  "Asia/Tokyo",
  "Pacific/Noumea",
  "Pacific/Tahiti",
  "Pacific/Wallis",
];

/** Fuseau lisible s'il est reconnu, sinon la chaîne POSIX de la caméra telle quelle ; `""` : sans fuseau. */
export function fuseauLu(horloge: Horloge): string {
  return horloge.fuseau ?? horloge.fuseau_posix ?? "";
}

/** Date et heure UTC de la caméra, au format français. */
export function texteDateHeure(dateHeureUtc: string): string {
  return new Date(dateHeureUtc).toLocaleString("fr-FR", { timeZone: "UTC" });
}

export type CleIncrustation = "nom" | "date_heure";

/** Champs modifiés d'une Incrustation : seuls ceux présents sont envoyés à la caméra. */
export type ModificationIncrustation = { affichee?: boolean; texte?: string; position?: Coin };

/** `horloge` absent : fuseau inchangé. */
export type Modification = {
  horloge?: { fuseau: string };
  incrustations: Partial<Record<CleIncrustation, ModificationIncrustation>>;
};

export type StatutChamp = "pris" | "pas_pris" | "refuse";

/** Résultat d'un champ envoyé : `champ` vaut `horloge.fuseau`, `incrustations.nom.texte`… ; fuseau relu en POSIX. */
export type ChampModifie = {
  champ: string;
  demande: string | boolean;
  relu: string | boolean | null;
  statut: StatutChamp;
};

export type ResultatModification = { champs: ChampModifie[]; reglages: Reglages };

/** Valeurs du formulaire d'une Incrustation ; `texte` ne sert qu'au nom. */
export type IncrustationSaisie = { affichee: boolean; texte: string; position: Position };

/** `fuseau` : nom IANA, ou fuseau inconnu de la caméra tel quel tant qu'il n'est pas changé. */
export type Saisie = { fuseau: string; incrustations: Record<CleIncrustation, IncrustationSaisie> };

// Coin proposé pour une Incrustation cachée qu'on réaffiche : celui de la caméra « sortie d'usine ».
const COINS_PAR_DEFAUT: Record<CleIncrustation, Coin> = { nom: "UpperLeft", date_heure: "LowerLeft" };

export function saisieDepuis(reglages: Reglages): Saisie {
  const { nom, date_heure } = reglages.incrustations;
  return {
    fuseau: fuseauLu(reglages.horloge),
    incrustations: {
      nom: { affichee: nom.affichee, texte: nom.texte ?? "", position: nom.position ?? COINS_PAR_DEFAUT.nom },
      date_heure: {
        affichee: date_heure.affichee,
        texte: "",
        position: date_heure.position ?? COINS_PAR_DEFAUT.date_heure,
      },
    },
  };
}

/**
 * Champs de `saisie` qui diffèrent de la caméra (`actuels`) ; une Incrustation réaffichée part avec texte et coin.
 * Le fuseau n'est envoyé que changé pour un fuseau de la liste.
 */
export function modificationsEntre(actuels: Reglages, saisie: Saisie): Modification {
  const incrustations: Modification["incrustations"] = {};
  for (const cle of ["nom", "date_heure"] as const) {
    const lue = actuels.incrustations[cle];
    const saisi = saisie.incrustations[cle];
    const champs: ModificationIncrustation = {};
    if (!saisi.affichee) {
      if (lue.affichee) champs.affichee = false;
    } else {
      const reaffichee = !lue.affichee;
      if (reaffichee) champs.affichee = true;
      if (cle === "nom" && (reaffichee || saisi.texte !== (lue as IncrustationNom).texte)) champs.texte = saisi.texte;
      if (saisi.position !== "Custom" && (reaffichee || saisi.position !== lue.position)) {
        champs.position = saisi.position;
      }
    }
    if (Object.keys(champs).length > 0) incrustations[cle] = champs;
  }
  if (saisie.fuseau === fuseauLu(actuels.horloge)) return { incrustations };
  return { horloge: { fuseau: saisie.fuseau }, incrustations };
}

export function estVide(modification: Modification): boolean {
  return !modification.horloge && Object.keys(modification.incrustations).length === 0;
}
