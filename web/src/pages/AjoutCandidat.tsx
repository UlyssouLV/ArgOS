import { useEffect, useId, useState, type FormEvent, type ReactNode } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LONGUEUR_MOT_DE_PASSE_SUR, messageEchec, motDePasseCourt, texteMac, type Camera } from "../cameras";
import {
  ajouterDepuisEssai,
  essayer,
  renouvelerEssai,
  retirerEssai,
  type Adresse,
  type DemandeEssai,
  type Essai,
  type Issue,
} from "../detection";
import { LecteurFlux } from "../LecteurFlux";

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

/** Codecs que le lecteur de Flux sait montrer : H.264 en WebRTC, H.265 en HLS. */
const CODECS_LUS: ReadonlyArray<string | null> = ["H264", "H265"];

/** Codec nommé comme on l'écrit (`H265` → « en H.265 ») ; inconnu : « dans un codec ». */
function messageCodec(codec: string | null): string {
  let nom = "dans un codec";
  if (codec) nom = `en ${codec.replace(/^H(\d{3})$/, "H.$1")}`;
  return `Cette caméra émet ${nom}, que le navigateur ne sait pas lire. La Caméra peut être ajoutée ; la lecture viendra dans une version future.`;
}

const MOT_DE_PASSE_COURT = `Mot de passe court (moins de ${LONGUEUR_MOT_DE_PASSE_SUR} caractères) : en ONVIF, la caméra le reçoit en empreinte (SHA-1, imposé par la norme), qui se casse hors ligne s'il est faible. L'ajout reste permis ; mieux vaut un mot de passe d'au moins ${LONGUEUR_MOT_DE_PASSE_SUR} caractères.`;

const APERCU_RETIRE = "L'Aperçu a été retiré (délai dépassé) : annuler puis recommencer.";

type PropsAjout = Readonly<{
  candidat: Adresse;
  /** Essai déjà fait (ajout par adresse IP) : le panneau ne relance pas le premier. */
  premierEssai?: Essai;
  onAjoutee: (camera: Camera) => void;
  onFermer: () => void;
}>;

/**
 * Panneau d'ajout, sous la ligne d'un Candidat ou sous « Ajouter par adresse IP » : essai (« Recherche du Flux… »), puis Aperçu, nom et emplacement.
 * Caméra à mot de passe : identifiant et mot de passe, puis « Valider ».
 * Flux introuvable : chemin RTSP saisi, essayé avec les identifiants déjà donnés, puis « Valider ».
 * L'Aperçu se lit comme le Live, d'après le codec de l'essai (H.265 en HLS, le reste en WebRTC).
 * Codec ni H.264 ni H.265 : message nommant le codec ; l'ajout reste permis.
 * Appareil qui porte déjà une Caméra (même MAC, autre chemin) : avertissement ; l'ajout reste permis.
 * Mot de passe court : avertissement à la saisie, puis au résultat de l'essai ; l'ajout reste permis.
 * L'Aperçu est renouvelé tant que le panneau est ouvert ; « Annuler » retire l'essai et son Aperçu,
 * l'ajout les retire côté serveur. Panneau quitté sans « Annuler » : l'Aperçu expire de lui-même.
 */
export function AjoutCandidat({ candidat, premierEssai, onAjoutee, onFermer }: PropsAjout) {
  const id = useId();
  const [essai, setEssai] = useState<Essai | null>(premierEssai ?? null);
  const [nom, setNom] = useState("");
  const [emplacement, setEmplacement] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  const [identifiant, setIdentifiant] = useState(IDENTIFIANT_PAR_DEFAUT);
  const [motDePasse, setMotDePasse] = useState("");
  // Vrai dès que des identifiants ont été envoyés : ils accompagnent ensuite chaque essai.
  const [avecIdentifiants, setAvecIdentifiants] = useState(false);
  // Le dernier essai a envoyé un mot de passe court : le champ est vidé une fois le Flux trouvé.
  const [essaiAvecMotDePasseCourt, setEssaiAvecMotDePasseCourt] = useState(false);
  const [chemin, setChemin] = useState("");

  const dejaEssaye = premierEssai !== undefined;
  useEffect(() => {
    if (dejaEssaye) return;
    let abandonne = false;
    essayer(candidat.ip, candidat.port)
      .then((resultat) => !abandonne && setEssai(resultat))
      .catch((e) => !abandonne && setErreur(messageEchec(e)));
    return () => {
      abandonne = true;
    };
  }, [candidat.ip, candidat.port, dejaEssaye]);

  /** Un seul essai d'identifiants par clic : ArgOS ne réessaie jamais seul. */
  async function reessayer() {
    setEssai(null);
    setErreur(null);
    try {
      const envoieIdentifiants = avecIdentifiants || identifiantsDemandes;
      setAvecIdentifiants(envoieIdentifiants);
      const demande: DemandeEssai = envoieIdentifiants ? { identifiant, mot_de_passe: motDePasse } : {};
      if (chemin.trim()) demande.chemin = chemin.trim();
      setEssaiAvecMotDePasseCourt(envoieIdentifiants && motDePasseCourt(motDePasse));
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
  const codecIllisible = apercu !== null && !CODECS_LUS.includes(codec);
  // À la saisie tant que les identifiants sont demandés, sinon au résultat de l'essai.
  const signalerMotDePasseCourt = identifiantsDemandes
    ? motDePasseCourt(motDePasse)
    : essai !== null && essaiAvecMotDePasseCourt;

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
    <form
      aria-label={`Ajouter ${candidat.ip}:${candidat.port}`}
      className="grid gap-3 rounded-lg border bg-card p-4"
      onSubmit={soumettre}
    >
      {essai === null && erreur === null && (
        <output className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
          Recherche du Flux…
        </output>
      )}
      {essai && essai.issue !== "flux_trouve" && <p className="text-destructive">{MESSAGES[essai.issue]}</p>}
      {essai && essai.issue !== "injoignable" && (
        <p className="font-mono text-xs text-muted-foreground">MAC de l'Appareil : {texteMac(essai.mac)}</p>
      )}
      {identifiantsDemandes && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Champ id={`${id}-identifiant`} libelle="Identifiant">
            <Input
              id={`${id}-identifiant`}
              name="identifiant"
              required
              autoComplete="off"
              value={identifiant}
              onChange={(e) => setIdentifiant(e.target.value)}
            />
          </Champ>
          <Champ id={`${id}-mot-de-passe`} libelle="Mot de passe">
            <Input
              id={`${id}-mot-de-passe`}
              name="mot_de_passe"
              type="password"
              autoComplete="new-password"
              value={motDePasse}
              onChange={(e) => setMotDePasse(e.target.value)}
            />
          </Champ>
        </div>
      )}
      {signalerMotDePasseCourt && <Avertissement>{MOT_DE_PASSE_COURT}</Avertissement>}
      {cheminDemande && (
        <Champ id={`${id}-chemin`} libelle="Chemin RTSP">
          <Input
            id={`${id}-chemin`}
            name="chemin"
            required
            autoComplete="off"
            placeholder="/chemin/du/flux"
            className="font-mono"
            value={chemin}
            onChange={(e) => setChemin(e.target.value)}
          />
        </Champ>
      )}
      {apercu && (
        <>
          <LecteurFlux
            cheminFlux={apercu}
            codec={codec}
            className="overflow-hidden rounded-md"
          />
          {codecIllisible && <p className="text-destructive">{messageCodec(codec)}</p>}
          {essai?.appareil_deja_connu && (
            <Avertissement>Cet appareil porte déjà la Caméra {essai.appareil_deja_connu.nom}</Avertissement>
          )}
          <div className="grid gap-3 sm:grid-cols-2">
            <Champ id={`${id}-nom`} libelle="Nom">
              <Input id={`${id}-nom`} name="nom" required value={nom} onChange={(e) => setNom(e.target.value)} />
            </Champ>
            <Champ id={`${id}-emplacement`} libelle="Emplacement">
              <Input
                id={`${id}-emplacement`}
                name="emplacement"
                placeholder="facultatif"
                value={emplacement}
                onChange={(e) => setEmplacement(e.target.value)}
              />
            </Champ>
          </div>
        </>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="outline" onClick={annuler}>
          Annuler
        </Button>
        {(identifiantsDemandes || cheminDemande) && <Button type="submit">Valider</Button>}
        {apercu && (
          <Button type="submit" disabled={envoi}>
            Ajouter la Caméra
          </Button>
        )}
      </div>
      {erreur && (
        <p role="alert" className="text-13 text-destructive">
          {erreur}
        </p>
      )}
    </form>
  );
}

function Champ({ id, libelle, children }: Readonly<{ id: string; libelle: string; children: ReactNode }>) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{libelle}</Label>
      {children}
    </div>
  );
}

function Avertissement({ children }: Readonly<{ children: ReactNode }>) {
  return <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-13">{children}</p>;
}
