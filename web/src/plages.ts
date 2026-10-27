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

/** Plus petite fenêtre demandée au Pont, en ms : un reste plus court d'un Segment ne se lit pas, il est sauté. */
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
 * Fenêtre depuis `instant` (ms) jusqu'à la fin de `intervalle` (un Segment) : `start` RFC 3339 et `duration` en
 * secondes ; `null` si `instant` est hors de l'intervalle ou à moins de `DUREE_MIN_FENETRE_MS` de sa fin.
 */
export function fenetreDans(intervalle: Intervalle, instant: number): Fenetre | null {
  const fin = Date.parse(intervalle.fin);
  // À la milliseconde, comme `start` : un clic tombe entre deux, et la fenêtre doit finir pile à la fin du Segment.
  const depart = Math.trunc(instant);
  const debut = Date.parse(intervalle.debut);
  if (depart < debut || fin - depart < DUREE_MIN_FENETRE_MS) return null;
  return {
    // Dans la milliseconde du début, `start` reprend le début du Segment, à la microseconde : arrondi, il le
    // précéderait et MediaMTX ne trouverait aucun Segment (404).
    start: depart === debut ? intervalle.debut : new Date(depart).toISOString(),
    duration: (fin - depart) / 1000,
  };
}

/**
 * Segments de `plage`, du plus ancien, chacun arrêté au début du suivant : sa dernière écriture peut le dépasser, et
 * le Pont mettrait alors les premières images du suivant dans la fenêtre.
 */
function segmentsDeLaPlage(segments: Intervalle[], plage: Intervalle): Intervalle[] {
  const debut = Date.parse(plage.debut);
  const fin = Date.parse(plage.fin);
  const dedans = segments
    .filter((segment) => debut <= Date.parse(segment.debut) && Date.parse(segment.debut) <= fin)
    .sort((a, b) => Date.parse(a.debut) - Date.parse(b.debut));
  return dedans.map((segment, i) => {
    const suivant = dedans[i + 1];
    return suivant && Date.parse(suivant.debut) < Date.parse(segment.fin) ? { ...segment, fin: suivant.debut } : segment;
  });
}

/**
 * Fenêtre depuis `instant` (ms) dans la Plage des Segments qui le couvre, qu'un Segment fermé depuis peut prolonger :
 * jusqu'à la fin de son Segment, jamais au-delà (#172), ou depuis le début du Segment suivant s'il en reste moins de
 * `DUREE_MIN_FENETRE_MS` ; `null` dans un trou ou à la fin de la Plage.
 */
export function fenetreDansLaPlage(segments: Intervalle[], instant: number): Fenetre | null {
  const plage = plageCourante(plagesEnregistrees(segments), instant);
  if (plage === null) return null;
  for (const segment of segmentsDeLaPlage(segments, plage)) {
    // Un Segment fini avant `instant` n'en donne pas ; l'écart d'écriture avant le suivant mène à son début.
    const fenetre = fenetreDans(segment, Math.max(instant, Date.parse(segment.debut)));
    if (fenetre !== null) return fenetre;
  }
  return null;
}

/**
 * Fenêtre à lire depuis `instant` (ms), un clic ou la fin d'une fenêtre lue (ADR 0018) : dans la Plage qui le couvre ;
 * sinon (trou, fin de Plage), dans le sens de lecture, au début de la Plage suivante du jour. `null` s'il n'y en a plus.
 */
export function fenetreDepuis(segments: Intervalle[], instant: number): Fenetre | null {
  const dedans = fenetreDansLaPlage(segments, instant);
  if (dedans !== null) return dedans;
  const suivante = plageSuivante(plagesEnregistrees(segments), instant);
  return suivante === null ? null : fenetreDansLaPlage(segments, Date.parse(suivante.debut));
}

/** Instant (ms) où s'achève une fenêtre ; arrondi : `duration` en secondes perdrait la milliseconde de fin de Plage. */
export function finDeFenetre({ start, duration }: Fenetre): number {
  return Date.parse(start) + Math.round(duration * 1000);
}

/** Deux fenêtres identiques demandent la même vidéo au Pont. */
export function memeFenetre(a: Fenetre | null, b: Fenetre | null): boolean {
  return a !== null && b !== null && a.start === b.start && a.duration === b.duration;
}

/**
 * Durée (s) de la vidéo d'une fenêtre : celle du MP4 servi, `dureeVideo`, une fois connue. Une Caméra dont le Pont jette
 * la vidéo du début de chaque Segment (Cam 01, #172) en sert moins que la fenêtre n'en couvre.
 */
function dureeLue(lue: Fenetre, dureeVideo: number | null): number {
  return dureeVideo !== null && Number.isFinite(dureeVideo) ? Math.min(lue.duration, dureeVideo) : lue.duration;
}

/** La fenêtre lue à `position` (s), à `vitesse`, finit dans `ANTICIPATION_S` de temps réel : sa suite se précharge. */
export function aRenouveler(lue: Fenetre, position: number, vitesse: number, dureeVideo: number | null = null): boolean {
  return (dureeLue(lue, dureeVideo) - position) / vitesse <= ANTICIPATION_S;
}

/**
 * Instant (ms) de l'image à `position` (s) de la fenêtre lue. Sa vidéo finit avec la fenêtre : plus courte que
 * celle-ci, elle commence d'autant plus tard que `start` (début de Segment perdu à l'enregistrement, #172).
 */
export function instantDeLaFenetre(lue: Fenetre, position: number, dureeVideo: number | null = null): number {
  return Date.parse(lue.start) + (lue.duration - dureeLue(lue, dureeVideo) + position) * 1000;
}
