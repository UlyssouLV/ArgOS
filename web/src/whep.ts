// Client WHEP minimal, en lecture seule : le Live lit le Flux d'une Caméra en WebRTC depuis MediaMTX.
// Pas d'iframe ni de HLS : la négociation est un POST de l'offre SDP, la réponse SDP revient en 201.

const PORT_WEBRTC = "8889";
/** Délai pour que la connexion s'établisse après la négociation, sinon c'est une coupure. */
const DELAI_CONNEXION_MS = 10_000;
/** Attente maximale des candidats ICE locaux avant d'envoyer l'offre (pas de trickle ICE). */
const DELAI_CANDIDATS_MS = 2_000;

/** MediaMTX est sur le même hôte que la page, comme l'API. */
export function urlWhep(cheminFlux: string): string {
  return `${window.location.protocol}//${window.location.hostname}:${PORT_WEBRTC}/${cheminFlux}/whep`;
}

function candidatsRassembles(pc: RTCPeerConnection): Promise<void> {
  if (pc.iceGatheringState === "complete") return Promise.resolve();
  return new Promise((resolve) => {
    const fin = setTimeout(resolve, DELAI_CANDIDATS_MS);
    pc.addEventListener("icegatheringstatechange", () => {
      if (pc.iceGatheringState === "complete") {
        clearTimeout(fin);
        resolve();
      }
    });
  });
}

/**
 * Ouvre une connexion WebRTC sur `url` et branche le Flux sur `video`.
 *
 * Rejette si la négociation échoue. Une fois négociée, `surCoupure` est appelée si la connexion
 * ne s'établit pas ou se coupe. `signal` ferme la connexion : il n'en reste aucune ouverte après.
 */
export async function lireWhep(
  url: string,
  video: HTMLVideoElement,
  surCoupure: () => void,
  signal: AbortSignal,
): Promise<void> {
  const pc = new RTCPeerConnection();
  let ressource: string | null = null;
  let delai: ReturnType<typeof setTimeout> | undefined;

  function fermer() {
    clearTimeout(delai);
    pc.onconnectionstatechange = null;
    pc.close();
    // La session côté MediaMTX se libère aussi d'elle-même à la fermeture : le DELETE l'anticipe.
    if (ressource) fetch(ressource, { method: "DELETE" }).catch(() => {});
    video.srcObject = null;
  }

  signal.throwIfAborted();
  signal.addEventListener("abort", fermer, { once: true });
  try {
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.ontrack = (evenement) => {
      video.srcObject = evenement.streams[0] ?? new MediaStream([evenement.track]);
    };
    await pc.setLocalDescription(await pc.createOffer());
    await candidatsRassembles(pc);

    const reponse = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/sdp" },
      body: pc.localDescription!.sdp,
      signal,
    });
    if (reponse.status !== 201) throw new Error(`Négociation WHEP refusée (${reponse.status})`);
    const location = reponse.headers.get("Location");
    if (location) ressource = new URL(location, url).href;
    await pc.setRemoteDescription({ type: "answer", sdp: await reponse.text() });
    signal.throwIfAborted();
  } catch (erreur) {
    if (!signal.aborted) fermer();
    throw erreur;
  }

  pc.onconnectionstatechange = () => {
    if (pc.connectionState === "failed" || pc.connectionState === "disconnected") surCoupure();
  };
  delai = setTimeout(() => {
    if (pc.connectionState !== "connected") surCoupure();
  }, DELAI_CONNEXION_MS);
}
