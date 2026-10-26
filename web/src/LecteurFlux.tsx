import { useEffect, useRef, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";
import { hevcDecodable, lireHls, urlHls, type EchecHls } from "./hls";
import { lireWhep, urlWhep } from "./whep";

const NOUVELLE_TENTATIVE_MS = 5_000;

export type EtatLecteur = "connexion" | "lecture" | "indisponible" | "codec_non_supporte";

type PropsLecteur = Readonly<{
  cheminFlux: string;
  /** Codec du Flux (`H265` → HLS ; tout autre, ou `null` si inconnu → WebRTC). */
  codec: string | null;
  /** Appelée à chaque changement d'état du lecteur. */
  onEtat?: (etat: EtatLecteur) => void;
  /** Classes du cadre (16/9 sur fond vidéo par défaut). */
  className?: string;
}>;

/**
 * Lit un Flux en WebRTC, ou en HLS s'il est en H.265 (docs/adr/0004-hls-pour-les-flux-h265.md).
 *
 * Pendant la connexion, un message le dit dans la vidéo. En cas d'échec ou de coupure, « Flux indisponible » et nouvelle tentative. Si le navigateur ne décode
 * pas le H.265, un message le dit, sans nouvelle tentative : réessayer n'y changerait rien.
 */
export function LecteurFlux({ cheminFlux, codec, onEtat, className }: PropsLecteur) {
  const video = useRef<HTMLVideoElement>(null);
  const [etat, setEtat] = useState<EtatLecteur>("connexion");
  const enHls = codec === "H265";

  useEffect(() => {
    onEtat?.(etat);
  }, [etat, onEtat]);

  useEffect(() => {
    let tentative: AbortController | null = null;
    let reprise: ReturnType<typeof setTimeout> | undefined;

    function echec(raison: EchecHls) {
      tentative?.abort(); // une seule connexion ouverte : la précédente est fermée avant de réessayer
      tentative = null;
      clearTimeout(reprise);
      if (raison === "codec") {
        setEtat("codec_non_supporte");
        return;
      }
      setEtat("indisponible");
      reprise = setTimeout(tenter, NOUVELLE_TENTATIVE_MS);
    }

    function tenter() {
      const courante = new AbortController();
      tentative = courante;
      const echecCourant = (raison: EchecHls) => tentative === courante && echec(raison);
      if (enHls) {
        lireHls(urlHls(cheminFlux), video.current!, echecCourant, courante.signal);
        return;
      }
      lireWhep(urlWhep(cheminFlux), video.current!, () => echecCourant("indisponible"), courante.signal).catch(() =>
        echecCourant("indisponible"),
      );
    }

    setEtat("connexion"); // le codec peut changer sous un même Flux : le transport aussi
    if (enHls && !hevcDecodable(video.current!)) setEtat("codec_non_supporte");
    else tenter();
    return () => {
      clearTimeout(reprise);
      tentative?.abort();
      tentative = null;
    };
  }, [cheminFlux, enHls]);

  return (
    <div className={cn("relative aspect-video bg-video", className)}>
      {/* La vidéo reste affichée sous le message : Chrome met en pause une vidéo muette invisible.
          En absolu : Safari ne résout pas `height: 100%` dans un cadre dimensionné par `aspect-ratio`, la vidéo y
          garderait sa hauteur native et recouvrirait ce qui suit. */}
      <video
        ref={video}
        className="absolute inset-0 size-full object-contain"
        autoPlay
        muted
        playsInline
        onPlaying={() => setEtat("lecture")}
      />
      {etat === "connexion" && <MessageLecteur>Connexion au Flux…</MessageLecteur>}
      {etat === "indisponible" && <MessageLecteur>Flux indisponible</MessageLecteur>}
      {etat === "codec_non_supporte" && <MessageLecteur>Ce navigateur ne lit pas le H.265</MessageLecteur>}
    </div>
  );
}

function MessageLecteur({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <p className="absolute inset-0 grid place-items-center bg-video/80 p-4 text-center text-muted-foreground">
      {children}
    </p>
  );
}
