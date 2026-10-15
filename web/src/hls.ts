// Lecteur HLS, en lecture seule : le Live et l'Aperçu lisent un Flux H.265 en LL-HLS fMP4 depuis MediaMTX,
// sans réencodage (docs/adr/0004-hls-pour-les-flux-h265.md). C'est le navigateur qui décode le HEVC.

import Hls from "hls.js";

import { appeler, NonConnecte, signalerNonConnecte } from "./api";

/** HLS relayé par l'origine du Site vers MediaMTX, sans mise en tampon (docs/adr/0005-…), après la session (docs/adr/0006-…). */
const PREFIXE_HLS = "/flux/hls";
/** Type MIME d'un Flux H.265 en fMP4 (profil Main), tel que demandé au navigateur avant de lire. */
const TYPE_HEVC = 'video/mp4; codecs="hvc1.1.6.L93.B0"';
/** Code d'erreur de la balise vidéo pour un décodage impossible (MediaError.MEDIA_ERR_DECODE). */
const ERREUR_DECODAGE = 3;

/** Pourquoi la lecture s'arrête : le navigateur ne décode pas le HEVC, ou le Flux ne vient pas. */
export type EchecHls = "codec" | "indisponible";

/** Sous la même origine que la page, comme l'API. */
export function urlHls(cheminFlux: string): string {
  return `${PREFIXE_HLS}/${cheminFlux}/index.m3u8`;
}

/** hls.js (Media Source Extensions) d'abord ; HLS natif (Safari sur iPhone) sinon. */
function natif(): boolean {
  return !Hls.isSupported();
}

/** Faux si l'API refuse la session (et l'UI revient alors à la connexion) ; vrai sinon, même si l'API ne répond pas. */
async function sessionValide(): Promise<boolean> {
  try {
    await appeler("/api/session");
    return true;
  } catch (erreur) {
    return !(erreur instanceof NonConnecte);
  }
}

/** Vrai si le navigateur dit décoder le HEVC, par le chemin de lecture qu'il prendra. */
export function hevcDecodable(video: HTMLVideoElement): boolean {
  if (natif()) return video.canPlayType(TYPE_HEVC) !== "";
  return typeof MediaSource !== "undefined" && MediaSource.isTypeSupported(TYPE_HEVC);
}

/**
 * Lit le Flux HLS de `url` dans `video`.
 *
 * `surEchec` est appelée sur une erreur fatale : `codec` si le décodage échoue,
 * `indisponible` pour une erreur réseau ou de playlist. `signal` ferme le lecteur : plus aucune requête après.
 * Une playlist ou un segment refusé (401) renvoie à la connexion : hls.js donne le code HTTP ; le HLS natif ne le
 * donne pas, alors un Flux qui ne vient plus fait vérifier la session à l'API avant d'être dit indisponible.
 */
export function lireHls(url: string, video: HTMLVideoElement, surEchec: (echec: EchecHls) => void, signal: AbortSignal): void {
  signal.throwIfAborted();

  if (natif()) {
    const surErreurVideo = () => {
      if (video.error?.code === ERREUR_DECODAGE) return surEchec("codec");
      sessionValide().then((valide) => {
        if (valide && !signal.aborted) surEchec("indisponible");
      });
    };
    video.addEventListener("error", surErreurVideo);
    video.src = url;
    signal.addEventListener(
      "abort",
      () => {
        video.removeEventListener("error", surErreurVideo);
        video.removeAttribute("src");
        video.load();
      },
      { once: true },
    );
    return;
  }

  const surErreurVideo = () => surEchec(video.error?.code === ERREUR_DECODAGE ? "codec" : "indisponible");
  video.addEventListener("error", surErreurVideo);
  const hls = new Hls({ lowLatencyMode: true });
  hls.on(Hls.Events.ERROR, (_evenement, donnees) => {
    if (donnees.response?.code === 401) signalerNonConnecte();
    else if (donnees.fatal) surEchec(donnees.type === Hls.ErrorTypes.MEDIA_ERROR ? "codec" : "indisponible");
  });
  signal.addEventListener(
    "abort",
    () => {
      video.removeEventListener("error", surErreurVideo);
      hls.destroy();
    },
    { once: true },
  );
  hls.loadSource(url);
  hls.attachMedia(video);
}
