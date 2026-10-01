import { useCallback, useEffect, useState, type FormEvent } from "react";

import { NonConnecte } from "../api";
import {
  creerCamera,
  listerCameras,
  modifierCamera,
  Refus,
  supprimerCamera,
  type Camera,
  type SaisieCamera,
} from "../cameras";

const RAFRAICHISSEMENT_MS = 10_000;
const SAISIE_VIDE: SaisieCamera = { nom: "", url_rtsp: "", emplacement: null };

/** Message à montrer pour un échec d'appel ; `null` si la session est fermée (la connexion s'affiche). */
function messageEchec(erreur: unknown): string | null {
  if (erreur instanceof NonConnecte) return null;
  if (erreur instanceof Refus) return erreur.message;
  return "L'API du Site ne répond pas. Réessayez dans un instant.";
}

function dateVerification(camera: Camera): string {
  return camera.etat_verifie_le ? new Date(camera.etat_verifie_le).toLocaleString("fr-FR") : "—";
}

export function Administration() {
  const [cameras, setCameras] = useState<Camera[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enEdition, setEnEdition] = useState<number | null>(null);
  const [aSupprimer, setASupprimer] = useState<number | null>(null);

  const rafraichir = useCallback(async () => {
    try {
      setCameras(await listerCameras());
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

  /** Action d'une ligne : son échec s'affiche au-dessus de la liste, puis la liste est relue. */
  async function agir(action: () => Promise<void>) {
    try {
      await action();
      setErreur(null);
    } catch (e) {
      setErreur(messageEchec(e));
    }
    await rafraichir();
  }

  async function creer(saisie: SaisieCamera) {
    await creerCamera(saisie);
    await rafraichir();
  }

  async function enregistrer(id: number, saisie: SaisieCamera) {
    await modifierCamera(id, saisie);
    setEnEdition(null);
    await rafraichir();
  }

  return (
    <section className="administration">
      <h1>Administration</h1>
      <h2>Nouvelle Caméra</h2>
      <FormulaireCamera titre="Nouvelle Caméra" initiale={SAISIE_VIDE} libelle="Créer" viderApres onValider={creer} />
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
      {cameras?.length === 0 && <p>Aucune Caméra : en créer une ci-dessus.</p>}
      <h2>Caméras</h2>
      {cameras && cameras.length > 0 && (
        <table className="cameras">
          <thead>
            <tr>
              <th>Nom</th>
              <th>Emplacement</th>
              <th>Hôte:port</th>
              <th>URL RTSP</th>
              <th>Active</th>
              <th>État</th>
              <th>Dernière vérification</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {cameras.map((camera) =>
              enEdition === camera.id ? (
                <tr key={camera.id}>
                  <td colSpan={8}>
                    <FormulaireCamera
                      titre={`Modifier ${camera.nom}`}
                      initiale={camera}
                      libelle="Enregistrer"
                      onValider={(saisie) => enregistrer(camera.id, saisie)}
                      onAnnuler={() => setEnEdition(null)}
                    />
                  </td>
                </tr>
              ) : (
                <tr key={camera.id}>
                  <td>{camera.nom}</td>
                  <td>{camera.emplacement ?? "—"}</td>
                  <td>
                    {camera.hote}:{camera.port}
                  </td>
                  <td className="url">{camera.url_rtsp}</td>
                  <td>{camera.active ? "active" : "désactivée"}</td>
                  <td>
                    <span className={`etat etat-${camera.etat}`}>{camera.etat}</span>
                  </td>
                  <td>{dateVerification(camera)}</td>
                  <td>
                    <div className="actions">
                      <ActionsCamera
                        camera={camera}
                        confirmation={aSupprimer === camera.id}
                        onModifier={() => setEnEdition(camera.id)}
                        onActiver={(active) => agir(() => modifierCamera(camera.id, { active }))}
                        onDemanderSuppression={(demande) => setASupprimer(demande ? camera.id : null)}
                        onSupprimer={() => agir(() => supprimerCamera(camera.id))}
                      />
                    </div>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      )}
    </section>
  );
}

type PropsActions = Readonly<{
  camera: Camera;
  confirmation: boolean;
  onModifier: () => void;
  onActiver: (active: boolean) => void;
  onDemanderSuppression: (demande: boolean) => void;
  onSupprimer: () => void;
}>;

/** Pas de suppression offerte sur une Caméra active ; sur une désactivée, seulement après confirmation. */
function ActionsCamera({ camera, confirmation, onModifier, onActiver, onDemanderSuppression, onSupprimer }: PropsActions) {
  if (confirmation) {
    return (
      <>
        <span>Supprimer définitivement ?</span>
        <button type="button" className="danger" onClick={onSupprimer}>
          Confirmer la suppression
        </button>
        <button type="button" onClick={() => onDemanderSuppression(false)}>
          Annuler
        </button>
      </>
    );
  }
  return (
    <>
      <button type="button" onClick={onModifier}>
        Modifier
      </button>
      {camera.active ? (
        <button type="button" onClick={() => onActiver(false)}>
          Désactiver
        </button>
      ) : (
        <>
          <button type="button" onClick={() => onActiver(true)}>
            Réactiver
          </button>
          <button type="button" className="danger" onClick={() => onDemanderSuppression(true)}>
            Supprimer
          </button>
        </>
      )}
    </>
  );
}

type PropsFormulaire = Readonly<{
  titre: string;
  initiale: SaisieCamera;
  libelle: string;
  viderApres?: boolean;
  onValider: (saisie: SaisieCamera) => Promise<void>;
  onAnnuler?: () => void;
}>;

/** Création ou modification : un refus de l'API (409 doublon, 422 URL invalide) s'affiche dans le formulaire. */
function FormulaireCamera({ titre, initiale, libelle, viderApres = false, onValider, onAnnuler }: PropsFormulaire) {
  const [nom, setNom] = useState(initiale.nom);
  // En modification, l'URL masquée est renvoyée telle quelle si elle n'est pas touchée.
  const [url, setUrl] = useState(initiale.url_rtsp);
  const [emplacement, setEmplacement] = useState(initiale.emplacement ?? "");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  async function valider(evenement: FormEvent) {
    evenement.preventDefault();
    setEnvoi(true);
    setErreur(null);
    try {
      await onValider({ nom, url_rtsp: url, emplacement: emplacement.trim() || null });
      if (viderApres) {
        setNom("");
        setUrl("");
        setEmplacement("");
      }
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form className="formulaire-camera" aria-label={titre} onSubmit={valider}>
      <label>
        <span>Nom</span>
        <input name="nom" required value={nom} onChange={(e) => setNom(e.target.value)} />
      </label>
      <label>
        <span>URL RTSP</span>
        <input
          name="url_rtsp"
          required
          placeholder="rtsp://utilisateur:motdepasse@hote:554/chemin"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
      </label>
      <label>
        <span>Emplacement</span>
        <input name="emplacement" placeholder="facultatif" value={emplacement} onChange={(e) => setEmplacement(e.target.value)} />
      </label>
      <div className="boutons">
        <button type="submit" disabled={envoi}>
          {libelle}
        </button>
        {onAnnuler && (
          <button type="button" onClick={onAnnuler}>
            Annuler
          </button>
        )}
      </div>
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
    </form>
  );
}
