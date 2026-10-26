// Plages enregistrées et fenêtre de lecture de la Relecture continue (docs/adr/0018-relecture-continue-fenetre-glissante.md).
// Logique pure, sans import d'exécution : `tests/web/test_plages.py` l'exécute directement sous Node.

/** Segment fermé ou Plage enregistrée : bornes RFC 3339. */
export type Intervalle = { debut: string; fin: string };

/** Fenêtre demandée au Pont : `start` RFC 3339, `duration` en secondes. */
export type Fenetre = { start: string; duration: number };

/**
 * Écart (ms) jusqu'auquel deux Segments qui se suivent restent contigus : la fin d'un Segment est la dernière écriture
 * de son fichier, le début du suivant la date de son nom. Même tolérance que l'assemblage de MediaMTX.
 */
export const TOLERANCE_CONTIGUITE_MS = 1_000;

/** Durée cible de la fenêtre de lecture (ADR 0018). */
export const DUREE_FENETRE_S = 180;

/** Plus petite fenêtre demandée au Pont, en ms : un reste plus court d'une Plage ne se lit pas, il est sauté. */
export const DUREE_MIN_FENETRE_MS = 1_000;

/** Temps réel (s) avant la fin d'une fenêtre où sa suite se précharge : assez pour un premier rendu du Pont. */
export const ANTICIPATION_S = 30;

/** Durée d'un intervalle, en secondes. */
export function dureeS({ debut, fin }: Intervalle): number {
  return (Date.parse(fin) - Date.parse(debut)) / 1000;
}

/** Plages enregistrées des Segments, du plus ancien : des Segments contigus en forment une seule, un trou les sépare. */
export function plagesEnregistrees(segments: Intervalle[]): Intervalle[] {
  const tries = [...segments].sort((a, b) => Date.parse(a.debut) - Date.parse(b.debut));
  const plages: Intervalle[] = [];
  for (const segment of tries) {
    const derniere = plages.at(-1);
    if (derniere && Date.parse(segment.debut) - Date.parse(derniere.fin) <= TOLERANCE_CONTIGUITE_MS) {
      if (Date.parse(segment.fin) > Date.parse(derniere.fin)) derniere.fin = segment.fin;
    } else {
      plages.push({ debut: segment.debut, fin: segment.fin });
    }
  }
  return plages;
}

/** Plage qui couvre `instant` (ms), bornes comprises ; `null` dans un trou. */
export function plageCourante(plages: Intervalle[], instant: number): Intervalle | null {
  return plages.find((plage) => Date.parse(plage.debut) <= instant && instant <= Date.parse(plage.fin)) ?? null;
}

/** Première Plage qui commence après `instant` (ms), dans le sens de lecture avant ; `null` s'il n'y en a plus. */
export function plageSuivante(plages: Intervalle[], instant: number): Intervalle | null {
  return plages.find((plage) => Date.parse(plage.debut) > instant) ?? null;
}

/**
 * Fenêtre depuis `instant` (ms) dans `plage` : `start` RFC 3339 et `duration` en secondes, environ `DUREE_FENETRE_S`,
 * coupée à la fin de la Plage pour ne pas englober un trou ; `null` si `instant` est hors de la Plage ou à moins de
 * `DUREE_MIN_FENETRE_MS` de sa fin.
 */
export function fenetreDans(plage: Intervalle, instant: number): Fenetre | null {
  const fin = Date.parse(plage.fin);
  // À la milliseconde, comme `start` : un clic tombe entre deux, et la fenêtre doit finir pile à la fin de la Plage.
  const depart = Math.trunc(instant);
  if (depart < Date.parse(plage.debut) || fin - depart < DUREE_MIN_FENETRE_MS) return null;
  return {
    start: new Date(depart).toISOString(),
    duration: Math.min(DUREE_FENETRE_S, (fin - depart) / 1000),
  };
}

/**
 * Fenêtre depuis `instant` (ms) dans la Plage des Segments qui le couvre, qu'un Segment fermé depuis peut prolonger ;
 * `null` dans un trou ou à la fin de la Plage.
 */
export function fenetreDansLaPlage(segments: Intervalle[], instant: number): Fenetre | null {
  const plage = plageCourante(plagesEnregistrees(segments), instant);
  return plage === null ? null : fenetreDans(plage, instant);
}

/**
 * Fenêtre à lire depuis `instant` (ms), un clic ou la fin d'une fenêtre lue (ADR 0018) : dans la Plage qui le couvre ;
 * sinon (trou, fin de Plage), dans le sens de lecture, au début de la Plage suivante du jour. `null` s'il n'y en a plus.
 */
export function fenetreDepuis(segments: Intervalle[], instant: number): Fenetre | null {
  const dedans = fenetreDansLaPlage(segments, instant);
  if (dedans !== null) return dedans;
  const suivante = plageSuivante(plagesEnregistrees(segments), instant);
  return suivante === null ? null : fenetreDans(suivante, Date.parse(suivante.debut));
}

/** Instant (ms) où s'achève une fenêtre ; arrondi : `duration` en secondes perdrait la milliseconde de fin de Plage. */
export function finDeFenetre({ start, duration }: Fenetre): number {
  return Date.parse(start) + Math.round(duration * 1000);
}

/** Deux fenêtres identiques demandent la même vidéo au Pont. */
export function memeFenetre(a: Fenetre | null, b: Fenetre | null): boolean {
  return a !== null && b !== null && a.start === b.start && a.duration === b.duration;
}

/** La fenêtre lue à `position` (s), à `vitesse`, finit dans `ANTICIPATION_S` de temps réel : sa suite se précharge. */
export function aRenouveler(lue: Fenetre, position: number, vitesse: number): boolean {
  return (lue.duration - position) / vitesse <= ANTICIPATION_S;
}
