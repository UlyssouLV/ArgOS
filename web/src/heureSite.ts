import { appeler } from "./api";

export type Source = "ntp" | "horloge_serveur";
export type SourceUtilisee = "ntp" | "horloge_serveur" | "non_synchronise" | "injoignable";

export type HeureDuSite = {
  source: Source;
  serveur_ntp: string;
  fuseau: string;
  fuseau_de_l_hote: boolean;
  source_utilisee: SourceUtilisee;
  reference: string | null;
  heure: string | null;
  adresse_serveur_de_temps: string | null;
  base_des_fuseaux: BaseDesFuseaux;
};

/** Base des fuseaux d'où viennent les décalages envoyés aux Caméras : celle du serveur, ou celle de l'image. */
export type BaseDesFuseaux = { version: string | null; origine: "hote" | "embarquee" };

export type ModificationHeureDuSite = Partial<Pick<HeureDuSite, "source" | "serveur_ntp" | "fuseau">>;

// Même motif que l'API : un nom DNS ou une IPv4.
export const MOTIF_SERVEUR_NTP = "[A-Za-z0-9]([A-Za-z0-9.\\-]{0,251}[A-Za-z0-9])?";

export async function lireHeureDuSite(): Promise<HeureDuSite> {
  const reponse = await appeler("/api/heure-du-site");
  if (!reponse.ok) throw new Error(`Lecture de l’Heure du Site : ${reponse.status}`);
  return reponse.json();
}

export async function modifierHeureDuSite(modification: ModificationHeureDuSite): Promise<HeureDuSite> {
  const reponse = await appeler("/api/heure-du-site", { method: "PATCH", body: JSON.stringify(modification) });
  if (reponse.status === 422) throw new Error("Réglage refusé : vérifier l’adresse du serveur NTP et le fuseau.");
  if (!reponse.ok) throw new Error(`Mise à jour de l’Heure du Site : ${reponse.status}`);
  return reponse.json();
}

/** Fuseaux proposés, Europe/Paris en tête : ceux que l'API sait relire sous le même nom. */
export async function lireFuseaux(): Promise<string[]> {
  const reponse = await appeler("/api/fuseaux");
  if (!reponse.ok) throw new Error(`Lecture des fuseaux : ${reponse.status}`);
  return reponse.json();
}

/** Ce que le Serveur de temps du Site sert vraiment aux Caméras. */
export function texteSourceUtilisee(heure: HeureDuSite): string {
  switch (heure.source_utilisee) {
    case "ntp":
      return `${heure.serveur_ntp} (serveur NTP${heure.reference ? `, suivi à ${heure.reference}` : ""})`;
    case "horloge_serveur":
      return heure.source === "ntp"
        ? `horloge du serveur (repli : ${heure.serveur_ntp} injoignable)`
        : "horloge du serveur";
    case "non_synchronise":
      return "en cours de synchronisation";
    default:
      return "Serveur de temps du Site injoignable";
  }
}

export function texteBaseDesFuseaux(base: BaseDesFuseaux): string {
  return `${base.version ?? "version inconnue"} (${base.origine === "hote" ? "serveur" : "embarquée dans ArgOS"})`;
}

/** Date et heure au fuseau du Site ; `null` : inconnue. */
export function texteHeure(dateUtc: Date | null, fuseau: string): string {
  if (dateUtc === null) return "inconnue";
  return dateUtc.toLocaleString("fr-FR", { timeZone: fuseau, dateStyle: "full", timeStyle: "medium" });
}

/** Date courte d'un tableau, au fuseau du Site (`undefined` tant qu'il n'est pas lu : celui du navigateur). */
export function dateCourteDuSite(iso: string, fuseau: string | undefined, timeStyle: "short" | "medium"): string {
  return new Date(iso).toLocaleString("fr-FR", { timeZone: fuseau, dateStyle: "short", timeStyle });
}

/** Dernière vérification de l'Horloge d'une Caméra active ; `etat` `null` : jamais vérifiée. */
export type EtatHorloge = "a_l_heure" | "ecart" | "sans_onvif" | "echec";

export type HorlogeVerifiee = {
  id: number;
  nom: string;
  etat: EtatHorloge | null;
  // Mesurés contre l'heure du Serveur de temps du Site : avant la Mise à l'heure (dérive), après (écart).
  derive_s: number | null;
  ecart_s: number | null;
  verifiee_le: string | null;
};

export async function lireHorlogesDesCameras(): Promise<HorlogeVerifiee[]> {
  const reponse = await appeler("/api/heure-du-site/cameras");
  if (!reponse.ok) throw new Error(`Lecture des Caméras : ${reponse.status}`);
  return reponse.json();
}

/** « Vérifier maintenant » : rend le tableau une fois toutes les Caméras actives vérifiées. */
export async function verifierLesCameras(): Promise<HorlogeVerifiee[]> {
  const reponse = await appeler("/api/heure-du-site/verification", { method: "POST" });
  if (!reponse.ok) throw new Error(`Vérification des Caméras : ${reponse.status}`);
  return reponse.json();
}

export function libelleEtatHorloge(etat: EtatHorloge | null): string {
  switch (etat) {
    case "a_l_heure":
      return "à l’heure";
    case "ecart":
      return "écart";
    case "sans_onvif":
      return "sans ONVIF";
    case "echec":
      return "échec";
    default:
      return "jamais vérifiée";
  }
}

/** Dérive ou écart mesuré, signé (positif : la Caméra avance) ; `—` sans mesure. */
export function texteEcart(ecartS: number | null): string {
  if (ecartS === null) return "—";
  const nombre = ecartS.toLocaleString("fr-FR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
    signDisplay: "always",
  });
  return `${nombre} s`;
}

/** Résultat de « Vérifier maintenant » en une phrase : nombre de Caméras par état, dans l'ordre du libellé. */
export function texteBilanVerification(horloges: HorlogeVerifiee[]): string {
  if (horloges.length === 0) return "Aucune Caméra active à vérifier.";
  const parEtat = new Map<string, number>();
  for (const { etat } of horloges) {
    const libelle = libelleEtatHorloge(etat);
    parEtat.set(libelle, (parEtat.get(libelle) ?? 0) + 1);
  }
  const detail = [...parEtat].map(([libelle, nombre]) => `${nombre} ${libelle}`).join(", ");
  return `Caméras vérifiées : ${detail}.`;
}
