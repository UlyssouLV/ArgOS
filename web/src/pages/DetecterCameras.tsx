import { useEffect, useState } from "react";

import { messageEchec } from "../cameras";
import {
  lancerDetection,
  lireEtatDetection,
  type Candidat,
  type EtatDetection,
  type ResultatDetection,
} from "../detection";

function couverture(sous_reseaux: string[], ports: number[]): string {
  return `${sous_reseaux.join(", ")} — ports ${ports.join(", ")}`;
}

function cle(candidat: Candidat): string {
  return `${candidat.ip}:${candidat.port}`;
}

/** Section de l'Administration : lance une Détection et montre les Candidats. Rien n'est ajouté ni stocké. */
export function DetecterCameras() {
  const [etat, setEtat] = useState<EtatDetection | null>(null);
  const [resultat, setResultat] = useState<ResultatDetection | null>(null);
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    lireEtatDetection()
      .then(setEtat)
      .catch((e) => setErreur(messageEchec(e)));
  }, []);

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
      {resultat && <Candidats resultat={resultat} />}
    </section>
  );
}

/** Nouveaux Candidats en tableau ; ceux déjà configurés à part, repliés, avec le nom de leur Caméra. */
function Candidats({ resultat }: { resultat: ResultatDetection }) {
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
            </tr>
          </thead>
          <tbody>
            {nouveaux.map((candidat) => (
              <tr key={cle(candidat)}>
                <td>{candidat.ip}</td>
                <td>{candidat.port}</td>
              </tr>
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
