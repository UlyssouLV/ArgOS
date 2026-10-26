import { useEffect, useState } from "react";
import { Navigate, NavLink, useParams } from "react-router";

import { AncienStyle } from "@/components/AncienStyle";
import { EnTeteDePage } from "@/components/EnTeteDePage";
import { listerCameras, messageEchec, type Camera } from "../cameras";
import { RelectureCamera } from "../RelectureCamera";

/** Relecture d'une Caméra (`/relecture/:idCamera`) ; `/relecture` seule ouvre la première. */
export function Relecture() {
  const { idCamera } = useParams();
  const [cameras, setCameras] = useState<Camera[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    let annule = false;
    listerCameras()
      .then((liste) => {
        if (!annule) setCameras(liste);
      })
      .catch((e: unknown) => {
        if (!annule) setErreur(messageEchec(e));
      });
    return () => {
      annule = true;
    };
  }, []);

  if (idCamera === undefined && cameras?.length) {
    return <Navigate to={`/relecture/${cameras[0].id}`} replace />;
  }
  const selectionnee = cameras?.find((camera) => String(camera.id) === idCamera);

  return (
    <>
      <EnTeteDePage titre="Relecture" />
      <AncienStyle>
        <section className="relecture-page">
          {erreur && (
            <p className="erreur" role="alert">
              {erreur}
            </p>
          )}
          {cameras?.length === 0 && <p>Aucune Caméra à relire.</p>}
          {cameras && cameras.length > 0 && (
            <nav aria-label="Caméras">
              {cameras.map((camera) => (
                <NavLink key={camera.id} to={`/relecture/${camera.id}`} className="camera-relecture">
                  {camera.nom}
                </NavLink>
              ))}
            </nav>
          )}
          {selectionnee && (
            <RelectureCamera key={selectionnee.id} idCamera={selectionnee.id} nom={selectionnee.nom} />
          )}
        </section>
      </AncienStyle>
    </>
  );
}
