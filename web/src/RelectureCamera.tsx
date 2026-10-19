import { useEffect, useRef, useState, type MouseEvent } from "react";

import { sessionValide } from "./api";
import { listerCameras, messageEchec } from "./cameras";
import { hevcDecodable } from "./hls";
import {
  VITESSES,
  dureeS,
  lireSegments,
  placeSurLaFenetre,
  segmentVise,
  urlRelecture,
  type SegmentsFermes,
  type Vitesse,
} from "./relecture";

type PropsRelecture = Readonly<{ idCamera: number; nom: string }>;

type EtatViewer = "lecture" | "indisponible" | "codec_non_supporte";

/** Chemin du pont d'une Caméra, aussi celui de ses enregistrements (`camera-<id>`, ADR 0011). */
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
  const [courant, setCourant] = useState<number | null>(null);
  const [etat, setEtat] = useState<EtatViewer>("lecture");
  const [vitesse, setVitesse] = useState<Vitesse>(1);
  const [enPause, setEnPause] = useState(true);
  const [position, setPosition] = useState(0);

  useEffect(() => {
    let annule = false;
    Promise.all([lireSegments(idCamera), listerCameras()])
      .then(([lue, cameras]) => {
        if (annule) return;
        setFenetre(lue);
        setCodec(cameras.find((c) => c.id === idCamera)?.codec ?? null);
      })
      .catch((e) => !annule && setErreur(messageEchec(e)));
    return () => {
      annule = true;
    };
  }, [idCamera]);

  const segment = fenetre !== null && courant !== null ? fenetre.segments[courant] : null;

  useEffect(() => {
    setPosition(0);
    if (segment === null) return;
    setEtat(codec === "H265" && !hevcDecodable(video.current!) ? "codec_non_supporte" : "lecture");
  }, [segment, codec]);

  useEffect(() => {
    if (video.current === null) return;
    video.current.defaultPlaybackRate = vitesse;
    video.current.playbackRate = vitesse;
  }, [vitesse]);

  function viser(event: MouseEvent<HTMLDivElement>) {
    if (fenetre === null) return;
    const boite = event.currentTarget.getBoundingClientRect();
    const fraction = (event.clientX - boite.left) / boite.width;
    const debut = Date.parse(fenetre.debut);
    const vise = segmentVise(fenetre.segments, debut + fraction * (Date.parse(fenetre.fin) - debut));
    if (vise === courant && video.current !== null) video.current.currentTime = 0;
    setCourant(vise);
  }

  function enchainer() {
    if (fenetre !== null && courant !== null && courant + 1 < fenetre.segments.length) setCourant(courant + 1);
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
      {fenetre && fenetre.segments.length === 0 && <p className="aide">Aucun enregistrement sur cette période</p>}
      {fenetre && fenetre.segments.length > 0 && (
        <>
          <div className="timeline-enregistrement" role="group" aria-label="Timeline d’enregistrement" onClick={viser}>
            {fenetre.segments.map((s, index) => {
              const { gauche, largeur } = placeSurLaFenetre(fenetre, s);
              return (
                <span
                  key={s.debut}
                  className={index === courant ? "plage-enregistree plage-courante" : "plage-enregistree"}
                  style={{ left: `${gauche}%`, width: `${largeur}%` }}
                  title={`${heure(s.debut)} → ${heure(s.fin)}`}
                />
              );
            })}
          </div>
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
              src={etat === "codec_non_supporte" ? undefined : urlRelecture(cheminFlux(idCamera), segment)}
              autoPlay
              muted
              playsInline
              onLoadedMetadata={(e) => {
                e.currentTarget.playbackRate = vitesse;
              }}
              onPlay={() => setEnPause(false)}
              onPause={() => setEnPause(true)}
              onTimeUpdate={(e) => setPosition(e.currentTarget.currentTime)}
              onEnded={enchainer}
              onError={surErreur}
            />
            {etat === "indisponible" && <p className="flux-indisponible">Enregistrement indisponible</p>}
            {etat === "codec_non_supporte" && <p className="flux-indisponible">Ce navigateur ne lit pas le H.265</p>}
          </div>
          <div className="commandes-relecture">
            <button type="button" onClick={basculer}>
              {enPause ? "Lecture" : "Pause"}
            </button>
            <progress aria-label="Progression dans le Segment" max={dureeS(segment)} value={position} />
            <span className="position">
              {minutesSecondes(position)} / {minutesSecondes(dureeS(segment))}
            </span>
            <span role="group" aria-label="Vitesse de lecture" className="vitesses">
              {VITESSES.map((v) => (
                <button key={v} type="button" aria-pressed={v === vitesse} onClick={() => setVitesse(v)}>
                  ×{v}
                </button>
              ))}
            </span>
          </div>
        </>
      )}
    </section>
  );
}
