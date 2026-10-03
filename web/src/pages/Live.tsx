import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";

import { listerCameras, messageEchec, type Camera } from "../cameras";
import { LecteurFlux } from "../LecteurFlux";

const RAFRAICHISSEMENT_MS = 10_000;

type CameraLive = Camera & { chemin_flux: string };

/** Caméras actives, dans l'ordre des noms : l'ordre du tour du Site. */
function camerasActives(cameras: Camera[]): CameraLive[] {
  return cameras
    .filter((camera): camera is CameraLive => camera.active && camera.chemin_flux !== null)
    .sort((a, b) => a.nom.localeCompare(b.nom, "fr"));
}

export function Live() {
  const [actives, setActives] = useState<CameraLive[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [idCourant, setIdCourant] = useState<number | null>(null);

  // Rafraîchit aussi le badge d'état de la Caméra affichée.
  const rafraichir = useCallback(async () => {
    try {
      setActives(camerasActives(await listerCameras()));
      setErreur(null);
    } catch (e) {
      setErreur(messageEchec(e));
    }
  }, []);

  useEffect(() => {
    void rafraichir();
    const minuterie = setInterval(() => void rafraichir(), RAFRAICHISSEMENT_MS);
    return () => clearInterval(minuterie);
  }, [rafraichir]);

  // Une Caméra désactivée entre deux rafraîchissements laisse place à la première.
  const courante = actives?.find((camera) => camera.id === idCourant) ?? actives?.[0] ?? null;

  const suivante = useCallback(() => {
    if (!actives?.length || courante === null) return;
    setIdCourant(actives[(actives.indexOf(courante) + 1) % actives.length].id);
  }, [actives, courante]);

  useEffect(() => {
    function auClavier(evenement: KeyboardEvent) {
      if (evenement.key === "ArrowRight") suivante();
    }
    window.addEventListener("keydown", auClavier);
    return () => window.removeEventListener("keydown", auClavier);
  }, [suivante]);

  return (
    <section className="live">
      <h1>Live</h1>
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
      {actives?.length === 0 && (
        <p>
          Aucune Caméra active. En ajouter ou en réactiver dans <Link to="/administration">Administration</Link>.
        </p>
      )}
      {courante && (
        <>
          <div className="live-en-tete">
            <h2>{courante.nom}</h2>
            <span className="emplacement">{courante.emplacement ?? "—"}</span>
            <span className={`etat etat-${courante.etat}`}>{courante.etat}</span>
            <button type="button" onClick={suivante}>
              Suivant
            </button>
          </div>
          {/* Une clé par Flux : changer de Caméra démonte le lecteur, qui ferme sa connexion WebRTC. */}
          <LecteurFlux key={courante.chemin_flux} cheminFlux={courante.chemin_flux} />
        </>
      )}
    </section>
  );
}
