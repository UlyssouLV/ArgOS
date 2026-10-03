import { Fragment, useEffect, useState } from "react";

import { messageEchec, type Camera } from "../cameras";
import {
  lancerDetection,
  lireEtatDetection,
  type Candidat,
  type EtatDetection,
  type ResultatDetection,
} from "../detection";
import { AjoutCandidat } from "./AjoutCandidat";

function couverture(sous_reseaux: string[], ports: number[]): string {
  return `${sous_reseaux.join(", ")} — ports ${ports.join(", ")}`;
}

function cle(candidat: Candidat): string {
  return `${candidat.ip}:${candidat.port}`;
}

/**
 * Section de l'Administration : lance une Détection, montre les Candidats et ajoute l'un d'eux comme Caméra.
 * `onCameraAjoutee` : la liste des Caméras est à relire.
 */
export function DetecterCameras({ onCameraAjoutee }: Readonly<{ onCameraAjoutee: () => void }>) {
  const [etat, setEtat] = useState<EtatDetection | null>(null);
  const [resultat, setResultat] = useState<ResultatDetection | null>(null);
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    lireEtatDetection()
      .then(setEtat)
      .catch((e) => setErreur(messageEchec(e)));
  }, []);

  /** Le Candidat passe dans « Déjà configurées » sans relancer de Détection. */
  function ajoutee(candidat: Candidat, camera: Camera) {
    setResultat((courant) =>
      courant && {
        ...courant,
        candidats: courant.candidats.map((c) =>
          cle(c) === cle(candidat) ? { ...c, camera: { id: camera.id, nom: camera.nom } } : c,
        ),
      },
    );
    onCameraAjoutee();
  }

  async function detecter() {
    setEnCours(true);
    setErreur(null);
    setResultat(null);
    try {
      setResultat(await lancerDetection());
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnCours(false);
    }
  }

  return (
    <section className="detection" aria-labelledby="titre-detection">
      <h2 id="titre-detection">Détecter des Caméras</h2>
      {etat?.configuree && <p>Sous-réseaux couverts : {couverture(etat.sous_reseaux, etat.ports)}</p>}
      {etat && !etat.configuree && <p className="erreur">{etat.raison}</p>}
      <button type="button" disabled={!etat?.configuree || enCours} onClick={detecter}>
        Détecter des Caméras
      </button>
      {enCours && <p role="status">Détection en cours…</p>}
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
      {resultat && <Candidats resultat={resultat} onAjoutee={ajoutee} />}
    </section>
  );
}

type PropsCandidats = Readonly<{
  resultat: ResultatDetection;
  onAjoutee: (candidat: Candidat, camera: Camera) => void;
}>;

/**
 * Nouveaux Candidats en tableau, chacun avec « Ajouter » : un seul panneau d'ajout ouvert à la fois, sous sa ligne.
 * Ceux déjà configurés à part, repliés, avec le nom de leur Caméra.
 */
function Candidats({ resultat, onAjoutee }: PropsCandidats) {
  const [enAjout, setEnAjout] = useState<string | null>(null);
  const nouveaux = resultat.candidats.filter((candidat) => candidat.camera === null);
  const configures = resultat.candidats.filter((candidat) => candidat.camera !== null);
  return (
    <>
      {nouveaux.length === 0 && (
        <p>
          Aucun {configures.length > 0 && "nouveau "}Candidat sur {couverture(resultat.sous_reseaux, resultat.ports)}.
        </p>
      )}
      {nouveaux.length > 0 && (
        <table className="cameras candidats" aria-label="Candidats">
          <thead>
            <tr>
              <th>IP</th>
              <th>Port</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {nouveaux.map((candidat) => (
              <Fragment key={cle(candidat)}>
                <tr>
                  <td>{candidat.ip}</td>
                  <td>{candidat.port}</td>
                  <td>
                    <button type="button" disabled={enAjout === cle(candidat)} onClick={() => setEnAjout(cle(candidat))}>
                      Ajouter
                    </button>
                  </td>
                </tr>
                {enAjout === cle(candidat) && (
                  <tr>
                    <td colSpan={3}>
                      <AjoutCandidat
                        candidat={candidat}
                        onAjoutee={(camera) => {
                          setEnAjout(null);
                          onAjoutee(candidat, camera);
                        }}
                        onFermer={() => setEnAjout(null)}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      )}
      {configures.length > 0 && (
        <details className="deja-configurees">
          <summary>Déjà configurées ({configures.length})</summary>
          <table className="cameras candidats" aria-label="Déjà configurées">
            <thead>
              <tr>
                <th>IP</th>
                <th>Port</th>
                <th>Caméra</th>
              </tr>
            </thead>
            <tbody>
              {configures.map((candidat) => (
                <tr key={cle(candidat)}>
                  <td>{candidat.ip}</td>
                  <td>{candidat.port}</td>
                  <td>{candidat.camera?.nom}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </>
  );
}
