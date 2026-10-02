import { useEffect, useState, type FormEvent } from "react";

import { messageEchec, type Camera } from "../cameras";
import { ajouterDepuisEssai, essayer, retirerEssai, type Candidat, type Essai, type Issue } from "../detection";
import { LecteurFlux } from "../LecteurFlux";

const MESSAGES: Record<Exclude<Issue, "flux_trouve">, string> = {
  identifiants_requis: "Cette caméra demande un mot de passe.",
  identifiants_refuses: "Identifiant ou mot de passe refusé par la caméra.",
  flux_introuvable: "Flux introuvable.",
  injoignable: "Aucune caméra ne répond à cette adresse.",
};

type PropsAjout = Readonly<{
  candidat: Candidat;
  onAjoutee: (camera: Camera) => void;
  onFermer: () => void;
}>;

/**
 * Panneau sous la ligne d'un Candidat : essai (« Recherche du Flux… »), puis Aperçu, nom et emplacement.
 * « Annuler » retire l'essai et son Aperçu ; l'ajout les retire côté serveur.
 */
export function AjoutCandidat({ candidat, onAjoutee, onFermer }: PropsAjout) {
  const [essai, setEssai] = useState<Essai | null>(null);
  const [nom, setNom] = useState("");
  const [emplacement, setEmplacement] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  useEffect(() => {
    let abandonne = false;
    essayer(candidat.ip, candidat.port)
      .then((resultat) => !abandonne && setEssai(resultat))
      .catch((e) => !abandonne && setErreur(messageEchec(e)));
    return () => {
      abandonne = true;
    };
  }, [candidat.ip, candidat.port]);

  async function ajouter(evenement: FormEvent) {
    evenement.preventDefault();
    setEnvoi(true);
    setErreur(null);
    try {
      onAjoutee(await ajouterDepuisEssai(nom, emplacement.trim() || null));
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnvoi(false);
    }
  }

  function annuler() {
    retirerEssai().catch(() => {});
    onFermer();
  }

  const apercu = essai?.issue === "flux_trouve" ? essai.apercu : null;
  return (
    <form className="ajout-candidat" aria-label={`Ajouter ${candidat.ip}:${candidat.port}`} onSubmit={ajouter}>
      {essai === null && erreur === null && <p role="status">Recherche du Flux…</p>}
      {essai && essai.issue !== "flux_trouve" && <p className="erreur">{MESSAGES[essai.issue]}</p>}
      {apercu && (
        <>
          <LecteurFlux cheminFlux={apercu} />
          <label>
            <span>Nom</span>
            <input name="nom" required value={nom} onChange={(e) => setNom(e.target.value)} />
          </label>
          <label>
            <span>Emplacement</span>
            <input name="emplacement" placeholder="facultatif" value={emplacement} onChange={(e) => setEmplacement(e.target.value)} />
          </label>
        </>
      )}
      <div className="boutons">
        {apercu && (
          <button type="submit" disabled={envoi}>
            Ajouter la Caméra
          </button>
        )}
        <button type="button" onClick={annuler}>
          Annuler
        </button>
      </div>
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
    </form>
  );
}
