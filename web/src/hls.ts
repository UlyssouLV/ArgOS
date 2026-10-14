// Lecteur HLS, en lecture seule : le Live et l'Aperçu lisent un Flux H.265 en LL-HLS fMP4 depuis MediaMTX,
// sans réencodage (docs/adr/0004-hls-pour-les-flux-h265.md). C'est le navigateur qui décode le HEVC.

import Hls from "hls.js";

import { signalerNonConnecte } from "./api";

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
 * Une playlist ou un segment refusé (401) renvoie à la connexion avec hls.js ; le HLS natif ne donne pas le code HTTP.
 */
export function lireHls(url: string, video: HTMLVideoElement, surEchec: (echec: EchecHls) => void, signal: AbortSignal): void {
  signal.throwIfAborted();
  const surErreurVideo = () => surEchec(video.error?.code === ERREUR_DECODAGE ? "codec" : "indisponible");
  video.addEventListener("error", surErreurVideo);

  if (natif()) {
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
