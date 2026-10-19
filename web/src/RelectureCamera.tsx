import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";

import { sessionValide } from "./api";
import { listerCameras, messageEchec } from "./cameras";
import { hevcDecodable } from "./hls";
import {
  VITESSES,
  dureeS,
  instantSurLaFenetre,
  lireSegments,
  placeSurLaFenetre,
  segmentSuivant,
  segmentVise,
  urlRelecture,
  type SegmentsFermes,
  type Vitesse,
} from "./relecture";

type PropsRelecture = Readonly<{ idCamera: number; nom: string }>;

type EtatViewer = "lisible" | "indisponible";

/** Les Segments fermés depuis rejoignent la timeline, et la fenêtre suit la Conservation. */
const RAFRAICHISSEMENT_MS = 10_000;

/**
 * Chemin du pont d'une Caméra, aussi celui de ses enregistrements (`camera-<id>`, ADR 0011). Recalculé ici :
 * l'API ne donne `chemin_flux` qu'à une Caméra activée, et une Caméra désactivée garde ses Segments.
 */
function cheminFlux(idCamera: number): string {
  return `camera-${idCamera}`;
}

function heure(iso: string): string {
  return new Date(iso).toLocaleTimeString("fr-FR");
}

function jourEtHeure(iso: string): string {
  return new Date(iso).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function minutesSecondes(s: number): string {
  const total = Math.max(0, Math.floor(s));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/**
 * Relecture d'une Caméra (docs/adr/0013-relecture-des-enregistrements.md) : Timeline d'enregistrement sur la
 * Conservation, puis viewer du Segment visé. Un clic part du début du Segment qui couvre l'instant, ou du plus
 * proche ; à la fin d'un Segment, le viewer enchaîne sur le suivant, à la même vitesse.
 */
export function RelectureCamera({ idCamera, nom }: PropsRelecture) {
  const video = useRef<HTMLVideoElement>(null);
  const [fenetre, setFenetre] = useState<SegmentsFermes | null>(null);
  const [codec, setCodec] = useState<string | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  // Segments repérés par leur début : un rafraîchissement décale leurs index.
  const [courant, setCourant] = useState<string | null>(null);
  const [acheve, setAcheve] = useState<string | null>(null);
  const [etat, setEtat] = useState<EtatViewer>("lisible");
  const [vitesse, setVitesse] = useState<Vitesse>(1);
  const [enPause, setEnPause] = useState(true);
  const [position, setPosition] = useState(0);

  useEffect(() => {
    let annule = false;
    const echec = (e: unknown) => !annule && setErreur(messageEchec(e));
    Promise.all([lireSegments(idCamera), listerCameras()])
      .then(([lue, cameras]) => {
        if (annule) return;
        setFenetre(lue);
        setCodec(cameras.find((c) => c.id === idCamera)?.codec ?? null);
      })
      .catch(echec);
    const minuterie = setInterval(() => {
      lireSegments(idCamera)
        .then((lue) => !annule && setFenetre(lue))
        .catch(echec);
    }, RAFRAICHISSEMENT_MS);
    return () => {
      annule = true;
      clearInterval(minuterie);
    };
  }, [idCamera]);

  const segment = fenetre?.segments.find((s) => s.debut === courant) ?? null;
  // Décidé avant de donner une source à la vidéo : sinon son échec masquerait le message (comme au Live).
  const h265Illisible = useMemo(
    () => codec === "H265" && !hevcDecodable(document.createElement("video")),
    [codec],
  );

  useEffect(() => {
    setPosition(0);
    setEtat("lisible");
  }, [courant]);

  // Fin du dernier Segment connu : on enchaîne dès qu'un rafraîchissement apporte le Segment fermé ensuite.
  useEffect(() => {
    if (fenetre === null || acheve === null) return;
    const suivant = segmentSuivant(fenetre.segments, acheve);
    if (suivant === null) return;
    setAcheve(null);
    setCourant(suivant.debut);
  }, [fenetre, acheve]);

  useEffect(() => {
    if (video.current === null) return;
    video.current.defaultPlaybackRate = vitesse;
    video.current.playbackRate = vitesse;
  }, [vitesse]);

  function debutVise(event: MouseEvent<HTMLButtonElement>, lue: SegmentsFermes): string | null {
    const { segments } = lue;
    // Au clavier (Entrée, Espace), pas de position : on passe au Segment suivant, ou au premier.
    if (event.detail === 0) {
      const suivant = courant === null ? null : segmentSuivant(segments, courant);
      return (suivant ?? segments[0]).debut;
    }
    const boite = event.currentTarget.getBoundingClientRect();
    const fraction = (event.clientX - boite.left) / boite.width;
    const vise = segmentVise(segments, instantSurLaFenetre(lue, fraction));
    return vise === null ? null : segments[vise].debut;
  }

  function viser(event: MouseEvent<HTMLButtonElement>) {
    if (fenetre === null) return;
    const debut = debutVise(event, fenetre);
    if (debut === null) return;
    if (debut === courant && video.current !== null) video.current.currentTime = 0;
    setAcheve(null);
    setCourant(debut);
  }

  function enchainer() {
    setAcheve(courant);
  }

  function surErreur() {
    // sessionValide ne rejette jamais : un 401 renvoie déjà à la connexion.
    void sessionValide().then((valide) => valide && setEtat("indisponible"));
  }

  function basculer() {
    const lecteur = video.current!;
    if (lecteur.paused) void lecteur.play().catch(() => {});
    else lecteur.pause();
  }

  return (
    <section className="relecture" aria-labelledby="titre-relecture">
      <h2 id="titre-relecture">Relecture — {nom}</h2>
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
      {fenetre?.segments.length === 0 && <p className="aide">Aucun enregistrement sur cette période</p>}
      {fenetre && fenetre.segments.length > 0 && (
        <>
          <button type="button" className="timeline-enregistrement" aria-label="Timeline d’enregistrement" onClick={viser}>
            {fenetre.segments.map((s) => {
              const { gauche, largeur } = placeSurLaFenetre(fenetre, s);
              return (
                <span
                  key={s.debut}
                  className={s.debut === courant ? "plage-enregistree plage-courante" : "plage-enregistree"}
                  style={{ left: `${gauche}%`, width: `${largeur}%` }}
                  title={`${heure(s.debut)} → ${heure(s.fin)}`}
                />
              );
            })}
          </button>
          <p className="bornes-timeline">
            <span>{jourEtHeure(fenetre.debut)}</span>
            <span>{jourEtHeure(fenetre.fin)}</span>
          </p>
          {segment === null && <p className="aide">Cliquez sur la timeline pour relire un Segment.</p>}
        </>
      )}
      {segment !== null && (
        <>
          <p className="segment-courant">
            Segment de {heure(segment.debut)} à {heure(segment.fin)}
          </p>
          <div className="lecteur">
            <video
              ref={video}
              src={h265Illisible ? undefined : urlRelecture(cheminFlux(idCamera), segment)}
              autoPlay
              muted
              playsInline
              onLoadedMetadata={(e) => {
                e.currentTarget.playbackRate = vitesse;
                // `autoPlay` seul ne part pas toujours sur un MP4 d'une minute (Chromium) : on lance la lecture.
                void e.currentTarget.play().catch(() => {});
              }}
              onPlay={() => setEnPause(false)}
              onPause={() => setEnPause(true)}
              onTimeUpdate={(e) => setPosition(e.currentTarget.currentTime)}
              onEnded={enchainer}
              onError={surErreur}
            />
            {h265Illisible && <p className="flux-indisponible">Ce navigateur ne lit pas le H.265</p>}
            {!h265Illisible && etat === "indisponible" && <p className="flux-indisponible">Enregistrement indisponible</p>}
          </div>
          {!h265Illisible && (
            <div className="commandes-relecture">
              <button type="button" onClick={basculer}>
                {enPause ? "Lecture" : "Pause"}
              </button>
              <progress aria-label="Progression dans le Segment" max={dureeS(segment)} value={position} />
              <span className="position">
                {minutesSecondes(position)} / {minutesSecondes(dureeS(segment))}
              </span>
              <fieldset className="vitesses">
                <legend>Vitesse de lecture</legend>
                {VITESSES.map((v) => (
                  <button key={v} type="button" aria-pressed={v === vitesse} onClick={() => setVitesse(v)}>
                    ×{v}
                  </button>
                ))}
              </fieldset>
            </div>
          )}
        </>
      )}
    </section>
  );
}
