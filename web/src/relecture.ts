// Relecture des Segments fermés d'une Caméra (docs/adr/0013-relecture-des-enregistrements.md) : la liste vient de
// l'API, la vidéo du serveur playback du pont, relayé par l'origine du Site derrière la session (ADR 0006).

import { appeler } from "./api";

/** Seule route du serveur playback relayée par nginx. */
const CHEMIN_RELECTURE = "/flux/relecture/get";
/** Plus petite durée demandée au pont, en secondes : un Segment très court reste lisible. */
const DUREE_MIN_S = 1;

export const VITESSES = [1, 2, 4, 8, 16] as const;
export type Vitesse = (typeof VITESSES)[number];

export type SegmentFerme = { debut: string; fin: string };

/** Fenêtre de Conservation (`debut` → `fin` = maintenant) et Segments fermés qui la touchent, du plus ancien. */
export type SegmentsFermes = { debut: string; fin: string; segments: SegmentFerme[] };

export async function lireSegments(idCamera: number): Promise<SegmentsFermes> {
  const reponse = await appeler(`/api/cameras/${idCamera}/segments`);
  if (!reponse.ok) throw new Error(`Lecture des Segments : ${reponse.status}`);
  return reponse.json();
}

export function dureeS(segment: SegmentFerme): number {
  return (Date.parse(segment.fin) - Date.parse(segment.debut)) / 1000;
}

/** MP4 du Segment entier, assemblé par le pont sans réencodage. */
export function urlRelecture(cheminFlux: string, segment: SegmentFerme): string {
  const parametres = new URLSearchParams({
    path: cheminFlux,
    start: segment.debut,
    duration: Math.max(dureeS(segment), DUREE_MIN_S).toFixed(3),
    format: "mp4",
  });
  return `${CHEMIN_RELECTURE}?${parametres}`;
}

/**
 * Index du Segment qui couvre `instant` (ms), sinon du plus proche ; `null` sans Segment.
 * La lecture part toujours du début de ce Segment : le seek précis attend la 1.0.0 (ADR 0013).
 */
export function segmentVise(segments: SegmentFerme[], instant: number): number | null {
  let vise: number | null = null;
  let ecartVise = Infinity;
  segments.forEach((segment, index) => {
    const ecart = Math.max(Date.parse(segment.debut) - instant, instant - Date.parse(segment.fin), 0);
    if (ecart < ecartVise) {
      vise = index;
      ecartVise = ecart;
    }
  });
  return vise;
}

/** Premier Segment qui commence après celui de début `debut` ; `null` s'il n'est pas encore fermé. */
export function segmentSuivant(segments: SegmentFerme[], debut: string): SegmentFerme | null {
  return segments.find((segment) => Date.parse(segment.debut) > Date.parse(debut)) ?? null;
}

/** Instant (ms) à une fraction de la fenêtre, de 0 (son début) à 1 (sa fin). */
export function instantSurLaFenetre(fenetre: SegmentsFermes, fraction: number): number {
  const debut = Date.parse(fenetre.debut);
  return debut + fraction * (Date.parse(fenetre.fin) - debut);
}

/** Place d'une plage sur la timeline, en pourcentage de la fenêtre, bornée à celle-ci. */
export function placeSurLaFenetre(fenetre: SegmentsFermes, segment: SegmentFerme): { gauche: number; largeur: number } {
  const debut = Date.parse(fenetre.debut);
  const total = Date.parse(fenetre.fin) - debut;
  const gauche = Math.max(0, (Date.parse(segment.debut) - debut) / total);
  const droite = Math.min(1, (Date.parse(segment.fin) - debut) / total);
  return { gauche: gauche * 100, largeur: Math.max(0, droite - gauche) * 100 };
}
