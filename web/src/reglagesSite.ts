import { appeler } from "./api";

export const CONSERVATION_MIN = 1;
export const CONSERVATION_MAX = 24;
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

/** Affiche une durée en secondes (heures / minutes). */
export function formaterDuree(secondes: number | null): string {
  if (secondes === null) return "—";
  const heures = secondes / 3600;
  if (heures >= 1) {
    return `${heures.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} h`;
  }
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
