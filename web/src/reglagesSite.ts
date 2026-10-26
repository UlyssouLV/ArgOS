import { appeler } from "./api";

export const CONSERVATION_MIN = 1;
export const CONSERVATION_MAX = 30 * 24; // 30 jours, stockés en heures (ADR 0017)
export const HEURES_PAR_JOUR = 24;
export const SEUIL_MIN_O = 104_857_600; // 100 Mo
export const SEUIL_DEFAUT_O = 1_073_741_824; // 1 Go
export const MO = 1_048_576;

export type ReglagesSite = {
  conservation_h: number;
  seuil_octets_libres: number;
};

export type EspaceEnregistrements = {
  total_o: number;
  libre_o: number;
  utilise_o: number;
  sous_seuil: boolean;
};

export type SourceDebit = "mesure" | "encodage" | "inconnu";

export type DebitCamera = {
  id: number;
  nom: string;
  active: boolean;
  enregistrement: boolean;
  etat_enregistrement: "enregistre" | "a_l_arret" | "en_erreur";
  debit_o_s: number | null;
  source_debit: SourceDebit;
  /** Début du plus ancien Segment conservé (ISO) ; `null` : aucun. */
  plus_ancien_segment: string | null;
};

export type DebitsEcriture = {
  cameras: DebitCamera[];
  debit_enregistrement_o_s: number | null;
  debit_projection_o_s: number | null;
  tenue_enregistrement_s: number | null;
  tenue_projection_s: number | null;
  conservation_s: number;
  tenue_enregistrement_ok: boolean | null;
  tenue_projection_ok: boolean | null;
};

export async function lireReglagesSite(): Promise<ReglagesSite> {
  const reponse = await appeler("/api/reglages-site");
  if (!reponse.ok) throw new Error(`Lecture des réglages Site : ${reponse.status}`);
  return reponse.json();
}

export async function modifierReglagesSite(champs: {
  conservation_h?: number;
  seuil_octets_libres?: number;
}): Promise<ReglagesSite> {
  const reponse = await appeler("/api/reglages-site", {
    method: "PATCH",
    body: JSON.stringify(champs),
  });
  if (!reponse.ok) throw new Error(`Mise à jour des réglages Site : ${reponse.status}`);
  return reponse.json();
}

/** La place libre ou le Seuil viennent de changer : la pastille du rail relit l'espace. */
export const EVENEMENT_ESPACE_MODIFIE = "argos:espace-modifie";

export function signalerEspaceModifie(): void {
  globalThis.dispatchEvent(new Event(EVENEMENT_ESPACE_MODIFIE));
}

export async function lireEspaceEnregistrements(): Promise<EspaceEnregistrements> {
  const reponse = await appeler("/api/espace-enregistrements");
  if (!reponse.ok) throw new Error(`Lecture de l'espace disque : ${reponse.status}`);
  return reponse.json();
}

export async function lireDebitsEcriture(): Promise<DebitsEcriture> {
  const reponse = await appeler("/api/debits-ecriture");
  if (!reponse.ok) throw new Error(`Lecture des débits d'écriture : ${reponse.status}`);
  return reponse.json();
}

/** Affiche une taille en octets de façon lisible (Mo / Go). */
export function formaterOctets(octets: number): string {
  if (octets >= 1_073_741_824) {
    return `${(octets / 1_073_741_824).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Go`;
  }
  return `${Math.round(octets / MO).toLocaleString("fr-FR")} Mo`;
}

/** Affiche un débit en o/s de façon lisible. */
export function formaterDebit(octetsParSeconde: number | null): string {
  if (octetsParSeconde === null) return "inconnu";
  if (octetsParSeconde >= MO) {
    return `${(octetsParSeconde / MO).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mo/s`;
  }
  if (octetsParSeconde >= 1000) {
    return `${Math.round(octetsParSeconde / 1000).toLocaleString("fr-FR")} Ko/s`;
  }
  return `${octetsParSeconde.toLocaleString("fr-FR")} o/s`;
}

/** Conservation en heures découpée pour la saisie jours + heures. */
export function joursEtHeures(heures: number): { jours: number; heures: number } {
  return { jours: Math.floor(heures / HEURES_PAR_JOUR), heures: heures % HEURES_PAR_JOUR };
}

/** Saisie jours + heures en heures de Conservation ; `null` : hors 1 h – 30 jours ou pas des entiers. */
export function conservationSaisie(jours: string, heures: string): number | null {
  const j = Number(jours === "" ? "0" : jours);
  const h = Number(heures === "" ? "0" : heures);
  if (!Number.isInteger(j) || !Number.isInteger(h) || j < 0 || h < 0 || h >= HEURES_PAR_JOUR) return null;
  const total = j * HEURES_PAR_JOUR + h;
  return total >= CONSERVATION_MIN && total <= CONSERVATION_MAX ? total : null;
}

/** Heures affichées en jours / heures : « 7 j », « 2 j 6 h », « 12 h ». */
export function formaterConservation(heures: number): string {
  const decoupe = joursEtHeures(heures);
  if (decoupe.jours === 0) return `${decoupe.heures} h`;
  const jours = `${decoupe.jours.toLocaleString("fr-FR")} j`;
  return decoupe.heures === 0 ? jours : `${jours} ${decoupe.heures} h`;
}

/** Affiche une durée en secondes (jours / heures, ou minutes sous l'heure). */
export function formaterDuree(secondes: number | null): string {
  if (secondes === null) return "—";
  if (secondes >= 3600) return formaterConservation(Math.floor(secondes / 3600));
  return `${Math.max(1, Math.round(secondes / 60)).toLocaleString("fr-FR")} min`;
}

export function libelleEtatEnregistrement(etat: DebitCamera["etat_enregistrement"]): string {
  switch (etat) {
    case "enregistre":
      return "enregistre";
    case "en_erreur":
      return "en erreur";
    default:
      return "à l'arrêt";
  }
}

export function libelleSourceDebit(source: SourceDebit): string {
  switch (source) {
    case "mesure":
      return "mesuré";
    case "encodage":
      return "estimé (encodage)";
    default:
      return "inconnu";
  }
}

export function libelleTenue(ok: boolean | null): string {
  if (ok === null) return "tenue inconnue";
  return ok ? "compatible avec la conservation" : "trop ambitieux pour la conservation";
}
