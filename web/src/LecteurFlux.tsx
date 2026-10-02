import { useEffect, useRef, useState } from "react";

import { lireWhep, urlWhep } from "./whep";

const NOUVELLE_TENTATIVE_MS = 5_000;

type EtatLecteur = "connexion" | "lecture" | "indisponible";

/** Lit un Flux en WebRTC ; en cas d'échec ou de coupure, « Flux indisponible » et nouvelle tentative. */
export function LecteurFlux({ cheminFlux }: Readonly<{ cheminFlux: string }>) {
  const video = useRef<HTMLVideoElement>(null);
  const [etat, setEtat] = useState<EtatLecteur>("connexion");

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
