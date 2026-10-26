// Relecture des Segments fermés d'une Caméra (docs/adr/0013-relecture-des-enregistrements.md), un jour du Site à la
// fois (ADR 0017) : la liste vient de l'API, la vidéo du serveur playback du pont, relayé par l'origine du Site
// derrière la session (ADR 0006).

import { appeler } from "./api";
import type { Fenetre, Intervalle } from "./plages";

/** Seule route du serveur playback relayée par nginx. */
const CHEMIN_RELECTURE = "/flux/relecture/get";

export const VITESSES = [1, 2, 4, 8, 16] as const;
export type Vitesse = (typeof VITESSES)[number];

export type SegmentFerme = Intervalle;

/**
 * Fenêtre de Conservation (`debut` → `fin` = maintenant) et ses jours au fuseau du Site (`premier_jour` →
 * `dernier_jour`, `AAAA-MM-JJ`) ; `jour` relu (`debut_jour` → `fin_jour`, 23 à 25 h) et ses Segments fermés.
 */
export type SegmentsFermes = {
  debut: string;
  fin: string;
  fuseau: string;
  premier_jour: string;
  dernier_jour: string;
  jour: string;
  debut_jour: string;
  fin_jour: string;
  segments: SegmentFerme[];
};

/** Segments d'un jour du Site (`AAAA-MM-JJ`) ; `null` : le jour courant. */
export async function lireSegments(idCamera: number, jour: string | null): Promise<SegmentsFermes> {
  const requete = jour === null ? "" : `?${new URLSearchParams({ jour })}`;
  const reponse = await appeler(`/api/cameras/${idCamera}/segments${requete}`);
  if (!reponse.ok) throw new Error(`Lecture des Segments : ${reponse.status}`);
  return reponse.json();
}

/** Jour civil décalé de `pas` jours (`AAAA-MM-JJ`), sans fuseau : seule la date compte. */
export function jourVoisin(jour: string, pas: number): string {
  const date = new Date(`${jour}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + pas);
  return date.toISOString().slice(0, 10);
}

/** `jour` est dans la Conservation : les dates `AAAA-MM-JJ` se comparent comme des chaînes. */
export function jourSelectionnable(lue: SegmentsFermes, jour: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(jour) && lue.premier_jour <= jour && jour <= lue.dernier_jour;
}

const CLE_DERNIERE_CAMERA = "argos.relecture.derniere-camera";

/** Dernière Caméra relue sur ce navigateur ; `null` si inconnue ou stockage indisponible. */
export function derniereCameraRelue(): number | null {
  try {
    const lue = Number(localStorage.getItem(CLE_DERNIERE_CAMERA));
    return Number.isInteger(lue) && lue > 0 ? lue : null;
  } catch {
    return null;
  }
}

export function retenirCameraRelue(idCamera: number): void {
  try {
    localStorage.setItem(CLE_DERNIERE_CAMERA, String(idCamera));
  } catch {
    // Navigation privée ou stockage bloqué : `/relecture` ouvrira la première Caméra.
  }
}

/** MP4 de la fenêtre, assemblé par le Pont sans réencodage, au-delà d'un Segment s'il le faut. */
export function urlRelecture(cheminFlux: string, { start, duration }: Fenetre): string {
  const parametres = new URLSearchParams({
    path: cheminFlux,
    start,
    duration: duration.toFixed(3),
    format: "mp4",
  });
  return `${CHEMIN_RELECTURE}?${parametres}`;
}

/** Instant (ms) à une fraction du jour, de 0 (00h) à 1 (24h). */
export function instantSurLeJour(lue: SegmentsFermes, fraction: number): number {
  const debut = Date.parse(lue.debut_jour);
  return debut + fraction * (Date.parse(lue.fin_jour) - debut);
}

/** Place d'un instant (ms) sur la timeline, en pourcentage du jour, bornée à celui-ci. */
export function placeDeLInstant(lue: SegmentsFermes, instant: number): number {
  const debut = Date.parse(lue.debut_jour);
  const fraction = (instant - debut) / (Date.parse(lue.fin_jour) - debut);
  return Math.min(1, Math.max(0, fraction)) * 100;
}

/** Place d'une Plage sur la timeline, en pourcentage du jour, bornée à celui-ci. */
export function placeSurLeJour(lue: SegmentsFermes, plage: Intervalle): { gauche: number; largeur: number } {
  const gauche = placeDeLInstant(lue, Date.parse(plage.debut));
  return { gauche, largeur: placeDeLInstant(lue, Date.parse(plage.fin)) - gauche };
}

const HEURE_MS = 3_600_000;
/** Une graduation toutes les trois heures du Site. */
const PAS_GRADUATION_H = 3;

/**
 * Graduations de la timeline, toutes les trois heures de l'heure du Site, en pourcentage du jour. Elles suivent la
 * durée réelle du jour : un jour de 23 ou 25 h saute ou répète une heure (ADR 0017).
 */
export function graduationsDuJour(lue: SegmentsFermes): { place: number; libelle: string }[] {
  const debut = Date.parse(lue.debut_jour);
  const total = Date.parse(lue.fin_jour) - debut;
  const format = new Intl.DateTimeFormat("fr-FR", { timeZone: lue.fuseau, hour: "numeric", hourCycle: "h23" });
  const graduations: { place: number; libelle: string }[] = [];
  for (let instant = debut; instant < debut + total; instant += HEURE_MS) {
    const heure = Number(format.formatToParts(instant).find((partie) => partie.type === "hour")?.value);
    if (heure % PAS_GRADUATION_H === 0) {
      graduations.push({ place: ((instant - debut) / total) * 100, libelle: `${String(heure).padStart(2, "0")}h` });
    }
  }
  graduations.push({ place: 100, libelle: "24h" });
  return graduations;
}
