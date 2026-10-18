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

/** Affiche une taille en octets de façon lisible (Mo / Go). */
export function formaterOctets(octets: number): string {
  if (octets >= 1_073_741_824) {
    return `${(octets / 1_073_741_824).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Go`;
  }
  return `${Math.round(octets / MO).toLocaleString("fr-FR")} Mo`;
}
