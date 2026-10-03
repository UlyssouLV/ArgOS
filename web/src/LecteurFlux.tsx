import { useEffect, useRef, useState } from "react";

import { lireWhep, urlWhep } from "./whep";

const NOUVELLE_TENTATIVE_MS = 5_000;

export type EtatLecteur = "connexion" | "lecture" | "indisponible";

type PropsLecteur = Readonly<{
  cheminFlux: string;
  /** Appelée à chaque changement d'état du lecteur. */
  onEtat?: (etat: EtatLecteur) => void;
}>;

/** Lit un Flux en WebRTC ; en cas d'échec ou de coupure, « Flux indisponible » et nouvelle tentative. */
export function LecteurFlux({ cheminFlux, onEtat }: PropsLecteur) {
  const video = useRef<HTMLVideoElement>(null);
  const [etat, setEtat] = useState<EtatLecteur>("connexion");

  useEffect(() => {
    onEtat?.(etat);
  }, [etat, onEtat]);

  useEffect(() => {
    let tentative: AbortController | null = null;
    let reprise: ReturnType<typeof setTimeout> | undefined;

    function echec() {
      tentative?.abort(); // une seule connexion ouverte : la précédente est fermée avant de réessayer
      tentative = null;
      setEtat("indisponible");
      clearTimeout(reprise);
      reprise = setTimeout(tenter, NOUVELLE_TENTATIVE_MS);
    }

    function tenter() {
      const courante = new AbortController();
      tentative = courante;
      lireWhep(urlWhep(cheminFlux), video.current!, () => tentative === courante && echec(), courante.signal).catch(
        () => tentative === courante && echec(),
      );
    }

    tenter();
    return () => {
      clearTimeout(reprise);
      tentative?.abort();
      tentative = null;
    };
  }, [cheminFlux]);

  return (
    <div className="lecteur">
      {/* La vidéo reste affichée sous le message : Chrome met en pause une vidéo muette invisible. */}
      <video ref={video} autoPlay muted playsInline onPlaying={() => setEtat("lecture")} />
      {etat === "indisponible" && <p className="flux-indisponible">Flux indisponible</p>}
    </div>
  );
}
