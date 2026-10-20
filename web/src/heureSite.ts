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
};

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

/** Date et heure au fuseau du Site ; `null` : inconnue. */
export function texteHeure(dateUtc: Date | null, fuseau: string): string {
  if (dateUtc === null) return "inconnue";
  return dateUtc.toLocaleString("fr-FR", { timeZone: fuseau, dateStyle: "full", timeStyle: "medium" });
}
