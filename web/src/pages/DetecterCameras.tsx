import { Fragment, useEffect, useState, type FormEvent } from "react";

import { messageEchec, type Camera } from "../cameras";
import {
  essayer,
  lancerDetection,
  lireEtatDetection,
  type Adresse,
  type Candidat,
  type Essai,
  type EtatDetection,
  type ResultatDetection,
} from "../detection";
import { AjoutCandidat } from "./AjoutCandidat";

function couverture(sous_reseaux: string[], ports: number[]): string {
  return `${sous_reseaux.join(", ")} — ports ${ports.join(", ")}`;
}

function cle(adresse: Adresse): string {
  return `${adresse.ip}:${adresse.port}`;
}

/** Port RTSP standard, prérempli pour l'ajout par adresse IP. */
const PORT_RTSP = 554;

/**
 * Panneau d'ajout ouvert : celui d'un Candidat détecté, ou d'une IP saisie avec son premier essai
 * (`numero` : chaque saisie ouvre un panneau neuf, même sur la même IP).
 */
type EnAjout = { cle: string } | { adresse: Adresse; essai: Essai; numero: number };

/**
 * Section de l'Administration : lance une Détection, montre les Candidats et ajoute l'un d'eux comme Caméra,
 * ou ajoute un appareil non détecté par son IP. Un seul panneau d'ajout ouvert à la fois.
 * `onCameraAjoutee` : la liste des Caméras est à relire.
 */
export function DetecterCameras({ onCameraAjoutee }: Readonly<{ onCameraAjoutee: () => void }>) {
  const [etat, setEtat] = useState<EtatDetection | null>(null);
  const [resultat, setResultat] = useState<ResultatDetection | null>(null);
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enAjout, setEnAjout] = useState<EnAjout | null>(null);

  useEffect(() => {
    lireEtatDetection()
      .then(setEtat)
      .catch((e) => setErreur(messageEchec(e)));
  }, []);

  /** Le Candidat passe dans « Déjà configurées » sans relancer de Détection. */
  function ajoutee(candidat: Adresse, camera: Camera) {
    setEnAjout(null);
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
      {resultat && (
        <Candidats
          resultat={resultat}
          enAjout={enAjout && "cle" in enAjout ? enAjout.cle : null}
          onOuvrir={(candidat) => setEnAjout({ cle: cle(candidat) })}
          onFermer={() => setEnAjout(null)}
          onAjoutee={ajoutee}
        />
      )}
      <AjoutParIp
        onEssai={(adresse, essai) =>
          setEnAjout((avant) => ({ adresse, essai, numero: (avant && "numero" in avant ? avant.numero : 0) + 1 }))
        }
      />
      {enAjout && "adresse" in enAjout && (
        <AjoutCandidat
          key={enAjout.numero}
          candidat={enAjout.adresse}
          premierEssai={enAjout.essai}
          onAjoutee={(camera) => ajoutee(enAjout.adresse, camera)}
          onFermer={() => setEnAjout(null)}
        />
      )}
    </section>
  );
}

type PropsAjoutParIp = Readonly<{ onEssai: (adresse: Adresse, essai: Essai) => void }>;

/**
 * « Ajouter par adresse IP » : appareil que la Détection n'a pas trouvé, même si elle n'est pas configurée.
 * Le premier essai part d'ici ; une adresse refusée (Caméra déjà configurée, hors du réseau local) s'affiche
 * dans ce formulaire sans ouvrir le panneau d'ajout.
 */
function AjoutParIp({ onEssai }: PropsAjoutParIp) {
  const [ip, setIp] = useState("");
  const [port, setPort] = useState(String(PORT_RTSP));
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  async function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    const adresse = { ip: ip.trim(), port: Number(port) };
    setEnCours(true);
    setErreur(null);
    try {
      onEssai(adresse, await essayer(adresse.ip, adresse.port));
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnCours(false);
    }
  }

  return (
    <form className="ajout-par-ip" aria-label="Ajouter par adresse IP" onSubmit={soumettre}>
      <h3>Ajouter par adresse IP</h3>
      <label>
        <span>Adresse IP</span>
        <input
          name="ip"
          required
          autoComplete="off"
          pattern="\d{1,3}(\.\d{1,3}){3}"
          title="Adresse IPv4, par exemple 192.168.1.64"
          placeholder="192.168.1.64"
          value={ip} onChange={(e) => setIp(e.target.value)} />
      </label>
      <label>
        <span>Port</span>
        <input name="port" type="number" required min={1} max={65535} value={port} onChange={(e) => setPort(e.target.value)} />
      </label>
      <div className="boutons">
        <button type="submit" disabled={enCours}>
          Ajouter
        </button>
      </div>
      {enCours && <output>Recherche du Flux…</output>}
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
    </form>
  );
}

type PropsCandidats = Readonly<{
  resultat: ResultatDetection;
  /** Clé du Candidat dont le panneau d'ajout est ouvert sous sa ligne. */
  enAjout: string | null;
  onOuvrir: (candidat: Candidat) => void;
  onFermer: () => void;
  onAjoutee: (candidat: Candidat, camera: Camera) => void;
}>;

/**
 * Nouveaux Candidats en tableau, chacun avec « Ajouter » : le panneau d'ajout s'ouvre sous sa ligne.
 * Ceux déjà configurés à part, repliés, avec le nom de leur Caméra.
 */
function Candidats({ resultat, enAjout, onOuvrir, onFermer, onAjoutee }: PropsCandidats) {
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
                    <button type="button" disabled={enAjout === cle(candidat)} onClick={() => onOuvrir(candidat)}>
                      Ajouter
                    </button>
                  </td>
                </tr>
                {enAjout === cle(candidat) && (
                  <tr>
                    <td colSpan={3}>
                      <AjoutCandidat
                        candidat={candidat}
                        onAjoutee={(camera) => onAjoutee(candidat, camera)}
                        onFermer={onFermer}
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
