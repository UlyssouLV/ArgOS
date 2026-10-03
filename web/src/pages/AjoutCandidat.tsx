import { useCallback, useEffect, useState, type FormEvent } from "react";

import { messageEchec, type Camera } from "../cameras";
import {
  ajouterDepuisEssai,
  essayer,
  renouvelerEssai,
  retirerEssai,
  type Candidat,
  type DemandeEssai,
  type Essai,
  type Issue,
} from "../detection";
import { LecteurFlux, type EtatLecteur } from "../LecteurFlux";

const MESSAGES: Record<Exclude<Issue, "flux_trouve">, string> = {
  identifiants_requis: "Cette caméra demande un mot de passe.",
  identifiants_refuses: "Identifiant ou mot de passe refusé par la caméra.",
  flux_introuvable: "Flux introuvable.",
  injoignable: "Aucune caméra ne répond à cette adresse.",
};

/** Identifiant le plus courant des caméras ; prérempli, modifiable. */
const IDENTIFIANT_PAR_DEFAUT = "admin";

/** Renouvellements par délai d'expiration : un renouvellement perdu ne fait pas expirer l'Aperçu. */
const RENOUVELLEMENTS_PAR_EXPIRATION = 4;

/** Seul codec vidéo que les navigateurs lisent tous en WebRTC. */
const CODEC_LISIBLE = "H264";

/** Codec nommé comme on l'écrit (`H265` → « en H.265 ») ; inconnu : « dans un codec ». */
function messageCodec(codec: string | null): string {
  let nom = "dans un codec";
  if (codec) nom = `en ${codec.replace(/^H(\d{3})$/, "H.$1")}`;
  return `Cette caméra émet ${nom}, que le navigateur ne sait pas lire. La Caméra peut être ajoutée ; la lecture viendra dans une version future.`;
}

const APERCU_RETIRE = "L'Aperçu a été retiré (délai dépassé) : annuler puis recommencer.";

type PropsAjout = Readonly<{
  candidat: Candidat;
  onAjoutee: (camera: Camera) => void;
  onFermer: () => void;
}>;

/**
 * Panneau sous la ligne d'un Candidat : essai (« Recherche du Flux… »), puis Aperçu, nom et emplacement.
 * Caméra à mot de passe : identifiant et mot de passe, puis « Réessayer ».
 * Flux introuvable : chemin RTSP saisi, essayé avec les identifiants déjà donnés, puis « Réessayer ».
 * Codec autre que H.264, ou Aperçu qui ne démarre pas : message nommant le codec ; l'ajout reste permis.
 * L'Aperçu est renouvelé tant que le panneau est ouvert ; « Annuler » retire l'essai et son Aperçu,
 * l'ajout les retire côté serveur. Panneau quitté sans « Annuler » : l'Aperçu expire de lui-même.
 */
export function AjoutCandidat({ candidat, onAjoutee, onFermer }: PropsAjout) {
  const [essai, setEssai] = useState<Essai | null>(null);
  const [nom, setNom] = useState("");
  const [emplacement, setEmplacement] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  const [identifiant, setIdentifiant] = useState(IDENTIFIANT_PAR_DEFAUT);
  const [motDePasse, setMotDePasse] = useState("");
  // Vrai dès que des identifiants ont été envoyés : ils accompagnent ensuite chaque essai.
  const [avecIdentifiants, setAvecIdentifiants] = useState(false);
  const [chemin, setChemin] = useState("");
  // L'Aperçu a-t-il déjà joué, ou échoué avant de jouer ? Remis à zéro à chaque essai.
  const [lecture, setLecture] = useState<"attente" | "lue" | "echec">("attente");

  useEffect(() => {
    let abandonne = false;
    essayer(candidat.ip, candidat.port)
      .then((resultat) => !abandonne && setEssai(resultat))
      .catch((e) => !abandonne && setErreur(messageEchec(e)));
    return () => {
      abandonne = true;
    };
  }, [candidat.ip, candidat.port]);

  /** Un seul essai d'identifiants par clic : ArgOS ne réessaie jamais seul. */
  async function reessayer() {
    setEssai(null);
    setErreur(null);
    setLecture("attente");
    try {
      const envoieIdentifiants = avecIdentifiants || identifiantsDemandes;
      setAvecIdentifiants(envoieIdentifiants);
      const demande: DemandeEssai = envoieIdentifiants ? { identifiant, mot_de_passe: motDePasse } : {};
      if (chemin.trim()) demande.chemin = chemin.trim();
      const resultat = await essayer(candidat.ip, candidat.port, demande);
      if (resultat.issue === "flux_trouve") setMotDePasse("");
      setEssai(resultat);
    } catch (e) {
      setErreur(messageEchec(e));
    }
  }

  async function ajouter() {
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
  const identifiantsDemandes = essai?.issue === "identifiants_requis" || essai?.issue === "identifiants_refuses";
  const cheminDemande = essai?.issue === "flux_introuvable";
  const expirationS = essai?.expiration_s;
  const codec = essai?.codec ?? null;
  const codecIllisible = apercu !== null && (codec !== CODEC_LISIBLE || lecture === "echec");

  const suivreLecture = useCallback((etat: EtatLecteur) => {
    if (etat === "lecture") setLecture("lue");
    else if (etat === "indisponible") setLecture((avant) => (avant === "lue" ? avant : "echec"));
  }, []);

  useEffect(() => {
    if (!apercu || !expirationS) return;
    const minuterie = setInterval(() => {
      renouvelerEssai()
        .then((encore) => {
          if (encore) return;
          clearInterval(minuterie);
          setErreur(APERCU_RETIRE);
        })
        // Coupure passagère : le renouvellement suivant réessaie avant l'expiration.
        .catch(() => {});
    }, (expirationS * 1000) / RENOUVELLEMENTS_PAR_EXPIRATION);
    return () => clearInterval(minuterie);
  }, [apercu, expirationS]);

  function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    if (apercu) void ajouter();
    else if (identifiantsDemandes || cheminDemande) void reessayer();
  }

  return (
    <form className="ajout-candidat" aria-label={`Ajouter ${candidat.ip}:${candidat.port}`} onSubmit={soumettre}>
      {essai === null && erreur === null && <output>Recherche du Flux…</output>}
      {essai && essai.issue !== "flux_trouve" && <p className="erreur">{MESSAGES[essai.issue]}</p>}
      {identifiantsDemandes && (
        <>
          <label>
            <span>Identifiant</span>
            <input name="identifiant" required autoComplete="off" value={identifiant} onChange={(e) => setIdentifiant(e.target.value)} />
          </label>
          <label>
            <span>Mot de passe</span>
            <input
              name="mot_de_passe"
              type="password"
              autoComplete="new-password"
              value={motDePasse}
              onChange={(e) => setMotDePasse(e.target.value)}
            />
          </label>
        </>
      )}
      {cheminDemande && (
        <label>
          <span>Chemin RTSP</span>
          <input
            name="chemin"
            required
            autoComplete="off"
            placeholder="/chemin/du/flux"
            value={chemin}
            onChange={(e) => setChemin(e.target.value)}
          />
        </label>
      )}
      {apercu && (
        <>
          <LecteurFlux cheminFlux={apercu} onEtat={suivreLecture} />
          {codecIllisible && <p className="erreur">{messageCodec(codec)}</p>}
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
        {(identifiantsDemandes || cheminDemande) && <button type="submit">Réessayer</button>}
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
