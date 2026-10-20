import { useEffect, useId, useRef, useState } from "react";

import { LONGUEUR_MOT_DE_PASSE_SUR, messageEchec, type Camera } from "../cameras";
import { LecteurFlux } from "../LecteurFlux";
import {
  accepterEnClair,
  COINS,
  COMPENSATION,
  COMPENSATIONS_IMAGE,
  empreinteCourte,
  empreinteGroupee,
  encodageHorsBornes,
  estVide,
  faireConfiance,
  INFRAROUGE,
  lireReglages,
  modificationsEntre,
  modifierReglages,
  oublierCertificat,
  PARAMETRES_IMAGE,
  pasDe,
  RefusOnvif,
  saisieDepuis,
  textePosition,
  texteResolution,
  type Bornes,
  type CertificatsCompares,
  type ChampEncodage,
  type ChampImage,
  type ChampModifie,
  type CleIncrustation,
  type IncrustationSaisie,
  type ModeCompensation,
  type ModeInfrarouge,
  type ParametreImage,
  type Position,
  type Reglages,
  type ReglagesLus,
  type Saisie,
  type SaisieEncodage,
  type SecuriteOnvif,
  type ValeursImage,
} from "../reglages";

type Props = Readonly<{ camera: Camera; onFermer: () => void }>;

/**
 * Réglages de la Caméra lus sur la caméra par ONVIF à l'ouverture ; Incrustations, Image et Encodage du Flux se
 * règlent (l'heure, elle, se règle pour le Site). Le Flux se lit en tête du panneau, comme dans le Live, pour voir l'effet d'un réglage ; fermer le
 * panneau arrête la lecture.
 * Un certificat changé, un HTTPS disparu ou une caméra sans HTTPS (ONVIF en clair non accepté) bloque les Réglages
 * jusqu'à la décision de l'Administrateur, puis relit.
 */
export function ReglagesCamera({ camera, onFermer }: Props) {
  const [lus, setLus] = useState<ReglagesLus | null>(null);
  const [echec, setEchec] = useState<unknown>(null);
  // Incrémentée après une décision sur le certificat ou l'ONVIF en clair : relit la caméra.
  const [lecture, setLecture] = useState(0);
  const panneau = useRef<HTMLElement>(null);

  // Ouvert sous sa ligne, le panneau peut tomber hors de la vue : Chrome ne lit pas une vidéo muette hors de l'écran.
  useEffect(() => {
    panneau.current?.scrollIntoView({ block: "nearest" });
  }, [camera.id]);

  useEffect(() => {
    let ouvert = true;
    lireReglages(camera.id).then(
      (origine) => ouvert && setLus(origine),
      (e: unknown) => ouvert && setEchec(e ?? new Error()),
    );
    return () => {
      ouvert = false;
    };
  }, [camera.id, lecture]);

  function relire() {
    setLus(null);
    setEchec(null);
    setLecture((n) => n + 1);
  }

  const refus = echec instanceof RefusOnvif ? echec : null;
  // Certificat changé, HTTPS indisponible et ONVIF en clair non accepté ont leur écran ; les autres échecs, leur message.
  const decision =
    refus?.code === "certificat_change" ||
    refus?.code === "https_indisponible" ||
    refus?.code === "en_clair_non_accepte";
  const erreur = echec === null || decision ? null : messageEchec(echec);

  return (
    <section ref={panneau} className="reglages" aria-label={`Réglages de ${camera.nom}`}>
      <div className="reglages-en-tete">
        <h3>Réglages de {camera.nom}</h3>
        <button type="button" onClick={onFermer}>
          Fermer
        </button>
      </div>
      {/* Une clé par Flux, comme le Live : un autre Flux démonte le lecteur, qui ferme sa connexion. */}
      {camera.chemin_flux && (
        <LecteurFlux key={camera.chemin_flux} cheminFlux={camera.chemin_flux} codec={camera.codec} />
      )}
      {!lus && echec === null && <p>Lecture de la caméra…</p>}
      {refus?.code === "certificat_change" && (
        <CertificatChange
          camera={camera}
          message={refus.message}
          certificat={refus.certificat}
          onDecide={relire}
        />
      )}
      {refus?.code === "https_indisponible" && (
        <HttpsIndisponible camera={camera} message={refus.message} onDecide={relire} />
      )}
      {refus?.code === "en_clair_non_accepte" && (
        <AccordEnClair camera={camera} message={refus.message} onDecide={relire} />
      )}
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
      {lus && <BandeauSecurite camera={camera} securite={lus.securite} onDecide={relire} />}
      {lus && <FormulaireReglages camera={camera} origine={lus} />}
    </section>
  );
}

/**
 * Échange chiffré : empreinte courte du Certificat de l'Appareil (entière au survol) et sa date ; « TLS ancien ».
 * ONVIF en clair : rappel, et retrait de l'accord.
 */
function BandeauSecurite({
  camera,
  securite,
  onDecide,
}: Readonly<{ camera: Camera; securite: SecuriteOnvif; onDecide: () => void }>) {
  if (!securite.chiffre)
    return <BandeauEnClair camera={camera} motDePasseCourt={securite.mot_de_passe_court} onDecide={onDecide} />;
  if (!securite.empreinte) return null;
  return (
    <section className="reglages-securite" aria-label="Sécurité de l'échange">
      <p>
        Échange chiffré (HTTPS). Certificat de l'Appareil <code title={securite.empreinte}>{empreinteCourte(securite.empreinte)}</code>
        {securite.empreinte_memorisee_le &&
          `, mémorisé le ${new Date(securite.empreinte_memorisee_le).toLocaleDateString("fr-FR")}`}
        .
      </p>
      {securite.tls_ancien && (
        <p className="avertissement">
          TLS ancien : la caméra ne propose que TLS 1.0 ou 1.1, des versions dépassées. L'échange reste chiffré, avec
          la clé mémorisée.
        </p>
      )}
    </section>
  );
}

/** Décision de l'Administrateur envoyée à l'API, puis relecture ; l'échec reste affiché sur place. */
function useDecision(onDecide: () => void) {
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  async function decider(action: () => Promise<void>) {
    setEnvoi(true);
    setErreur(null);
    try {
      await action();
      onDecide();
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnvoi(false);
    }
  }

  return { envoi, erreur, decider };
}

/**
 * Réglages en ONVIF en clair, accepté par l'Administrateur : rappelé à chaque ouverture, et révocable.
 * Mot de passe court : rappelé aussi, puisque son empreinte passe en clair.
 */
function BandeauEnClair({
  camera,
  motDePasseCourt,
  onDecide,
}: Readonly<{ camera: Camera; motDePasseCourt: boolean; onDecide: () => void }>) {
  const { envoi, erreur, decider } = useDecision(onDecide);
  return (
    <section className="reglages-securite reglages-en-clair" aria-label="Sécurité de l'échange">
      <p className="avertissement">
        ONVIF en clair : cette caméra ne propose pas HTTPS. Le mot de passe (en empreinte) et les réglages passent en
        clair sur le réseau des caméras.
      </p>
      {motDePasseCourt && (
        <p className="avertissement">
          Mot de passe court (moins de {LONGUEUR_MOT_DE_PASSE_SUR} caractères) : son empreinte (SHA-1, imposé par la
          norme), qui passe ici en clair, se casse hors ligne. Mieux vaut un mot de passe d'au moins{" "}
          {LONGUEUR_MOT_DE_PASSE_SUR} caractères, sur la caméra puis dans l'URL de la Caméra.
        </p>
      )}
      <button type="button" disabled={envoi} onClick={() => void decider(() => accepterEnClair(camera.id, false))}>
        Retirer l'accord ONVIF en clair
      </button>
      {erreur && <p className="erreur">{erreur}</p>}
    </section>
  );
}

type PropsRefus = Readonly<{ camera: Camera; message: string; onDecide: () => void }>;

/**
 * La caméra ne propose pas HTTPS : seule la recherche du port lui est parvenue. « Régler quand même en clair »
 * mémorise l'accord pour cette Caméra, révocable depuis le bandeau.
 */
function AccordEnClair({ camera, message, onDecide }: PropsRefus) {
  const { envoi, erreur, decider } = useDecision(onDecide);
  return (
    <section className="reglages-refus" aria-label="ONVIF en clair">
      <p className="erreur" role="alert">
        {message}
      </p>
      <p>
        La régler quand même ferait passer son mot de passe (en empreinte, cassable hors ligne s'il est faible) et ses
        réglages en clair sur le réseau des caméras : qui l'écoute peut les lire ou les modifier au passage. Rien n'a
        été envoyé avec ses identifiants.
      </p>
      <button type="button" disabled={envoi} onClick={() => void decider(() => accepterEnClair(camera.id, true))}>
        Régler quand même en clair
      </button>
      {erreur && <p className="erreur">{erreur}</p>}
    </section>
  );
}

function texteEmpreinte(empreinte: string | null): string {
  return empreinte ? empreinteGroupee(empreinte) : "inconnu";
}

/**
 * La caméra présente une autre clé que celle mémorisée : rien d'authentifié n'est parti. Les deux empreintes et les
 * causes possibles ; « Faire confiance au nouveau certificat », confirmé, n'accepte que l'empreinte montrée ici.
 */
function CertificatChange({
  camera,
  message,
  certificat,
  onDecide,
}: PropsRefus & Readonly<{ certificat: CertificatsCompares | null }>) {
  const [confirmation, setConfirmation] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const presentee = certificat?.empreinte_presentee ?? null;

  async function confier(empreinte: string) {
    setEnvoi(true);
    setErreur(null);
    try {
      await faireConfiance(camera.id, empreinte);
      onDecide();
    } catch (e) {
      setErreur(messageEchec(e));
      setConfirmation(false);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <section className="reglages-refus" aria-label="Certificat changé">
      <p className="erreur" role="alert">
        {message}
      </p>
      <dl>
        <dt>Certificat mémorisé</dt>
        <dd>
          <code>{texteEmpreinte(certificat?.empreinte_memorisee ?? null)}</code>
          {certificat?.empreinte_memorisee_le &&
            `, le ${new Date(certificat.empreinte_memorisee_le).toLocaleDateString("fr-FR")}`}
        </dd>
        <dt>Certificat présenté</dt>
        <dd>
          <code>{texteEmpreinte(presentee)}</code>
        </dd>
      </dl>
      <p>
        Causes possibles : remise en usine, nouveau firmware, autre appareil à cette adresse. Rien n'est envoyé à la
        caméra avec ses identifiants tant que vous n'avez pas tranché.
      </p>
      {presentee && !confirmation && (
        <button type="button" disabled={envoi} onClick={() => setConfirmation(true)}>
          Faire confiance au nouveau certificat
        </button>
      )}
      {presentee && confirmation && (
        <p className="confirmation">
          <span>
            ArgOS réglera cette caméra avec le certificat <code>{empreinteCourte(presentee)}</code> et refusera
            l'ancien. Ne le faites que si vous savez pourquoi il a changé.
          </span>
          <button type="button" className="danger" disabled={envoi} onClick={() => void confier(presentee)}>
            Confirmer la confiance
          </button>
          <button type="button" disabled={envoi} onClick={() => setConfirmation(false)}>
            Annuler
          </button>
        </p>
      )}
      {erreur && <p className="erreur">{erreur}</p>}
    </section>
  );
}

/** La Caméra répondait en HTTPS et ne le fait plus : pas de repli en clair ; « Oublier le certificat » repart de zéro. */
function HttpsIndisponible({ camera, message, onDecide }: PropsRefus) {
  const { envoi, erreur, decider } = useDecision(onDecide);

  return (
    <section className="reglages-refus" aria-label="HTTPS indisponible">
      <p className="erreur" role="alert">
        {message}
      </p>
      <p>
        Causes possibles : remise en usine, nouveau firmware, autre appareil à cette adresse, ou quelqu'un qui bloque
        HTTPS pour lire l'échange en clair. Oublier le certificat fait repartir le contact suivant de zéro.
      </p>
      <button type="button" disabled={envoi} onClick={() => void decider(() => oublierCertificat(camera.id))}>
        Oublier le certificat de cette caméra
      </button>
      {erreur && <p className="erreur">{erreur}</p>}
    </section>
  );
}

// Libellés de chaque Incrustation : « Texte du nom », « Cacher la date et heure »…
const LIBELLES: Record<
  CleIncrustation,
  { titre: string; de: string; article: string }
> = {
  nom: { titre: "Nom", de: "du nom", article: "le nom" },
  date_heure: {
    titre: "Date et heure",
    de: "de la date et heure",
    article: "la date et heure",
  },
};

type PropsFormulaire = Readonly<{ camera: Camera; origine: Reglages }>;

/**
 * Formulaire des Réglages (Incrustations, Image, Encodage) : « Enregistrer » n'envoie que ce qui diffère de la caméra,
 * puis montre le statut de chaque champ envoyé ; « Annuler » revient aux valeurs d'origine, lues à l'ouverture et
 * toujours affichées. Un envoi qui touche l'Encodage coupe le Flux : il se confirme.
 */
function FormulaireReglages({ camera, origine }: PropsFormulaire) {
  // Dernières valeurs lues sur la caméra : à l'ouverture, puis relues après chaque envoi.
  const [actuels, setActuels] = useState(origine);
  const [saisie, setSaisie] = useState<Saisie>(() => saisieDepuis(origine));
  const [statuts, setStatuts] = useState<Record<string, ChampModifie>>({});
  const [aCacher, setACacher] = useState<CleIncrustation | null>(null);
  const [coupure, setCoupure] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const modification = modificationsEntre(actuels, saisie);
  const horsBornes = encodageHorsBornes(actuels.encodage, saisie.encodage);

  function changer(cle: CleIncrustation, champs: Partial<IncrustationSaisie>) {
    setSaisie((avant) => ({
      ...avant,
      incrustations: { ...avant.incrustations, [cle]: { ...avant.incrustations[cle], ...champs } },
    }));
  }

  function changerAffichage(cle: CleIncrustation, affichee: boolean) {
    // Cacher une Incrustation affichée sur la caméra se confirme : certaines ne savent pas la recréer.
    if (!affichee && actuels.incrustations[cle].affichee) setACacher(cle);
    else changer(cle, { affichee });
  }

  async function enregistrer() {
    setCoupure(false);
    setEnvoi(true);
    setErreur(null);
    try {
      const resultat = await modifierReglages(camera.id, modification);
      setActuels(resultat.reglages);
      setStatuts(
        Object.fromEntries(
          resultat.champs.map((champ) => [champ.champ, champ]),
        ),
      );
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form
      className="reglages-formulaire"
      onSubmit={(e) => {
        e.preventDefault();
        // L'Encodage coupe le Flux quelques secondes : confirmé avant l'envoi, pas l'Image ni les Incrustations.
        if (modification.encodage) setCoupure(true);
        else void enregistrer();
      }}
    >
      <div className="reglages-valeurs">
        <section aria-label="Incrustations">
          <h4>Incrustations</h4>
          {(["nom", "date_heure"] as const).map((cle) => (
            <ChampsIncrustation
              key={cle}
              cle={cle}
              origine={origine}
              actuels={actuels}
              saisie={saisie.incrustations[cle]}
              statuts={statuts}
              confirmation={aCacher === cle}
              nomArgos={camera.nom}
              onChanger={(champs) => changer(cle, champs)}
              onAffichage={(affichee) => changerAffichage(cle, affichee)}
              onConfirmerCacher={(confirme) => {
                if (confirme) changer(cle, { affichee: false });
                setACacher(null);
              }}
            />
          ))}
        </section>
        <ChampsImage
          origine={origine.image.valeurs}
          actuels={actuels}
          saisie={saisie.image}
          statuts={statuts}
          onChanger={(champs) =>
            setSaisie((avant) => ({ ...avant, image: avant.image && { ...avant.image, ...champs } }))
          }
        />
        <ChampsEncodage
          origine={origine.encodage}
          actuels={actuels}
          saisie={saisie.encodage}
          horsBornes={horsBornes}
          statuts={statuts}
          onChanger={(champs) =>
            setSaisie((avant) => ({ ...avant, encodage: avant.encodage && { ...avant.encodage, ...champs } }))
          }
        />
      </div>
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
      {coupure && (
        <p className="confirmation">
          <span>Le Flux de cette Caméra sera coupé quelques secondes.</span>
          <button type="button" className="danger" onClick={() => void enregistrer()}>
            Couper le Flux et enregistrer
          </button>
          <button type="button" onClick={() => setCoupure(false)}>
            Garder le Flux
          </button>
        </p>
      )}
      <div className="reglages-actions">
        <button type="submit" disabled={envoi || coupure || estVide(modification) || horsBornes.length > 0}>
          {envoi ? "Envoi à la caméra…" : "Enregistrer"}
        </button>
        <button
          type="button"
          disabled={envoi}
          onClick={() => {
            setSaisie(saisieDepuis(origine));
            setACacher(null);
            setCoupure(false);
            setStatuts({});
          }}
        >
          Annuler
        </button>
      </div>
    </form>
  );
}

type PropsChamps = Readonly<{
  cle: CleIncrustation;
  origine: Reglages;
  actuels: Reglages;
  saisie: IncrustationSaisie;
  statuts: Record<string, ChampModifie>;
  confirmation: boolean;
  nomArgos: string;
  onChanger: (champs: Partial<IncrustationSaisie>) => void;
  onAffichage: (affichee: boolean) => void;
  onConfirmerCacher: (confirme: boolean) => void;
}>;

function ChampsIncrustation({
  cle,
  origine,
  actuels,
  saisie,
  statuts,
  confirmation,
  nomArgos,
  onChanger,
  onAffichage,
  onConfirmerCacher,
}: PropsChamps) {
  const { titre, de, article } = LIBELLES[cle];
  const id = useId();
  const lue = origine.incrustations[cle];
  // « Afficher » n'est proposé que si l'Incrustation l'est déjà ou si la caméra sait la recréer.
  const actuelle = actuels.incrustations[cle];
  const peutAfficher = actuelle.affichee || actuelle.peut_etre_reaffichee;
  const statut = (champ: string, libelle: string) => (
    <StatutChamp
      resultat={statuts[`incrustations.${cle}.${champ}`]}
      libelle={`${libelle} ${de}`}
    />
  );

  return (
    <fieldset>
      <legend>{titre}</legend>
      <label htmlFor={`${id}-affichage`}>Affichage {de}</label>
      <select
        id={`${id}-affichage`}
        value={saisie.affichee ? "affichee" : "cachee"}
        onChange={(e) => onAffichage(e.target.value === "affichee")}
      >
        {(peutAfficher || saisie.affichee) && (
          <option value="affichee">affichée</option>
        )}
        <option value="cachee">cachée</option>
      </select>
      <Origine valeur={lue.affichee ? "affichée" : "cachée"} />
      {statut("affichee", "affichage")}
      {confirmation && (
        <p className="confirmation">
          <span>
            Certaines caméras ne permettent pas de la réafficher ensuite.
          </span>
          <button
            type="button"
            className="danger"
            onClick={() => onConfirmerCacher(true)}
          >
            Cacher {article}
          </button>
          <button type="button" onClick={() => onConfirmerCacher(false)}>
            Garder {article}
          </button>
        </p>
      )}
      {cle === "nom" && (
        <>
          <label htmlFor={`${id}-texte`}>Texte {de}</label>
          <input
            id={`${id}-texte`}
            type="text"
            value={saisie.texte}
            disabled={!saisie.affichee}
            onChange={(e) => onChanger({ texte: e.target.value })}
          />
          <button
            type="button"
            disabled={!saisie.affichee}
            onClick={() => onChanger({ texte: nomArgos })}
          >
            Reprendre le nom ArgOS
          </button>
          <Origine valeur={origine.incrustations.nom.texte ?? "—"} />
          {statut("texte", "texte")}
        </>
      )}
      {cle === "date_heure" && (
        <p>Format : {origine.incrustations.date_heure.format ?? "—"}</p>
      )}
      <label htmlFor={`${id}-position`}>Position {de}</label>
      <select
        id={`${id}-position`}
        value={saisie.position}
        disabled={!saisie.affichee}
        onChange={(e) => onChanger({ position: e.target.value as Position })}
      >
        {saisie.position === "Custom" && (
          <option value="Custom">{textePosition("Custom")}</option>
        )}
        {COINS.map((coin) => (
          <option key={coin} value={coin}>
            {textePosition(coin)}
          </option>
        ))}
      </select>
      <Origine valeur={textePosition(lue.position)} />
      {statut("position", "position")}
    </fieldset>
  );
}

// Libellés des champs d'Image : « Luminosité », « Statut : luminosité »…
const LIBELLES_IMAGE: Record<ChampImage, string> = {
  infrarouge: "Filtre infrarouge",
  luminosite: "Luminosité",
  contraste: "Contraste",
  saturation: "Saturation",
  nettete: "Netteté",
  contre_jour: "Contre-jour",
  contre_jour_niveau: "Niveau du contre-jour",
  wdr: "WDR",
  wdr_niveau: "Niveau du WDR",
};

type PropsImage = Readonly<{
  origine: ValeursImage | null;
  actuels: Reglages;
  saisie: ValeursImage | null;
  statuts: Record<string, ChampModifie>;
  onChanger: (champs: Partial<ValeursImage>) => void;
}>;

/**
 * Image de l'Appareil, partagée par ses Caméras : seuls les paramètres que la caméra propose, curseurs bornés par
 * elle, avec la valeur chiffrée et celle d'origine. Sans service image : « Image non réglable sur cette caméra ».
 */
function ChampsImage({ origine, actuels, saisie, statuts, onChanger }: PropsImage) {
  const id = useId();
  const options = actuels.image.options;
  if (!actuels.image.reglable || !options || !origine || !saisie) {
    return (
      <section aria-label="Image">
        <h4>Image</h4>
        <p>Image non réglable sur cette caméra</p>
      </section>
    );
  }
  const statut = (champ: ChampImage) => (
    <StatutChamp resultat={statuts[`image.${champ}`]} libelle={LIBELLES_IMAGE[champ].toLowerCase()} />
  );
  const curseur = (champ: ParametreImage | `${"contre_jour" | "wdr"}_niveau`, bornes: Bornes | null) => {
    const valeur = saisie[champ];
    if (!bornes || valeur === null) return null;
    return (
      <div key={champ}>
        <label htmlFor={`${id}-${champ}`}>{LIBELLES_IMAGE[champ]}</label>
        <input
          id={`${id}-${champ}`}
          type="range"
          min={bornes.min}
          max={bornes.max}
          step={pasDe(bornes)}
          value={valeur}
          onChange={(e) => onChanger({ [champ]: Number(e.target.value) })}
        />
        {/* Pas d'`<output>` : son rôle implicite `status` le confondrait avec le statut d'un envoi. */}
        <span className="valeur-curseur">{valeur}</span>
        <Origine valeur={texteNombre(origine[champ])} />
        {statut(champ)}
      </div>
    );
  };

  return (
    <section aria-label="Image">
      <h4>Image</h4>
      <p>Partagée par les Caméras de cet Appareil : la régler ici la règle pour chacune.</p>
      {options.infrarouge && saisie.infrarouge && (
        <div>
          <label htmlFor={`${id}-infrarouge`}>{LIBELLES_IMAGE.infrarouge}</label>
          <select
            id={`${id}-infrarouge`}
            value={saisie.infrarouge}
            onChange={(e) => onChanger({ infrarouge: e.target.value as ModeInfrarouge })}
          >
            {options.infrarouge.map((mode) => (
              <option key={mode} value={mode}>
                {INFRAROUGE[mode]}
              </option>
            ))}
          </select>
          <Origine valeur={origine.infrarouge ? INFRAROUGE[origine.infrarouge] : "—"} />
          {statut("infrarouge")}
        </div>
      )}
      {PARAMETRES_IMAGE.map((champ) => curseur(champ, options[champ]))}
      {COMPENSATIONS_IMAGE.map((champ) => {
        const modes = options[champ];
        const mode = saisie[champ];
        if (!modes || !mode) return null;
        return (
          <div key={champ}>
            <label htmlFor={`${id}-${champ}`}>{LIBELLES_IMAGE[champ]}</label>
            <select
              id={`${id}-${champ}`}
              value={mode}
              onChange={(e) => onChanger({ [champ]: e.target.value as ModeCompensation })}
            >
              {modes.map((m) => (
                <option key={m} value={m}>
                  {COMPENSATION[m]}
                </option>
              ))}
            </select>
            <Origine valeur={origine[champ] ? COMPENSATION[origine[champ]] : "—"} />
            {statut(champ)}
            {curseur(`${champ}_niveau`, options[`${champ}_niveau`])}
          </div>
        );
      })}
    </section>
  );
}

// Libellés des champs d'Encodage réglables : « Résolution », « Statut : débit max »…
const LIBELLES_ENCODAGE: Record<ChampEncodage, string> = {
  resolution: "Résolution",
  images_par_seconde: "Images par seconde",
  debit_max: "Débit max (kbit/s)",
};

const STATUTS_ENCODAGE: Record<ChampEncodage, string> = {
  resolution: "résolution",
  images_par_seconde: "images par seconde",
  debit_max: "débit max",
};

type PropsEncodage = Readonly<{
  origine: Reglages["encodage"];
  actuels: Reglages;
  saisie: SaisieEncodage | null;
  horsBornes: ChampEncodage[];
  statuts: Record<string, ChampModifie>;
  onChanger: (champs: Partial<SaisieEncodage>) => void;
}>;

/**
 * Encodage du Flux (profil de l'URL RTSP) : résolution parmi celles proposées, images par seconde et débit dans les
 * bornes de la caméra ; codec, qualité et intervalle entre images clés en lecture seule. Non réglable : valeurs en
 * lecture seule, et pourquoi.
 */
function ChampsEncodage({ origine, actuels, saisie, horsBornes, statuts, onChanger }: PropsEncodage) {
  const id = useId();
  const encodage = actuels.encodage;
  const valeurs = encodage.valeurs;
  if (!valeurs) {
    return (
      <section aria-label="Encodage du Flux">
        <h4>Encodage du Flux</h4>
        <p>
          {encodage.raison === "profil_introuvable"
            ? "Encodage introuvable pour ce Flux"
            : "Encodage non réglable sur cette caméra"}
        </p>
      </section>
    );
  }
  const options = encodage.options;
  const reglable = encodage.reglable && options && saisie;
  const statut = (champ: ChampEncodage) => (
    <StatutChamp resultat={statuts[`encodage.${champ}`]} libelle={STATUTS_ENCODAGE[champ]} />
  );
  const nombre = (champ: "images_par_seconde" | "debit_max") => {
    const bornes = options?.[champ];
    if (!reglable || !bornes) return null;
    const valeur = saisie[champ];
    return (
      <div>
        <label htmlFor={`${id}-${champ}`}>{LIBELLES_ENCODAGE[champ]}</label>
        <input
          id={`${id}-${champ}`}
          type="number"
          min={bornes.min}
          max={bornes.max}
          step={pasDe(bornes)}
          value={Number.isNaN(valeur) ? "" : valeur}
          onChange={(e) => onChanger({ [champ]: e.target.value === "" ? Number.NaN : Number(e.target.value) })}
        />
        <Origine valeur={texteNombre(origine.valeurs?.[champ] ?? null)} />
        {horsBornes.includes(champ) && (
          <span className="erreur">
            hors des bornes de la caméra ({bornes.min} à {bornes.max})
          </span>
        )}
        {statut(champ)}
      </div>
    );
  };

  return (
    <section aria-label="Encodage du Flux">
      <h4>Encodage du Flux</h4>
      {!reglable && <p>Encodage non réglable sur cette caméra</p>}
      <dl>
        <dt>Profil</dt>
        <dd>{encodage.profil ?? "—"}</dd>
        {!reglable && (
          <>
            <dt>Résolution</dt>
            <dd>{texteResolution(valeurs.resolution)}</dd>
            <dt>Images par seconde</dt>
            <dd>{texteNombre(valeurs.images_par_seconde)}</dd>
            <dt>Débit max (kbit/s)</dt>
            <dd>{texteNombre(valeurs.debit_max)}</dd>
          </>
        )}
        <dt>Codec</dt>
        <dd>{valeurs.codec}</dd>
        <dt>Qualité</dt>
        <dd>{texteNombre(valeurs.qualite)}</dd>
        <dt>Intervalle entre images clés</dt>
        <dd>{texteNombre(valeurs.intervalle_images_cles)}</dd>
      </dl>
      {reglable && (
        <>
          <div>
            <label htmlFor={`${id}-resolution`}>{LIBELLES_ENCODAGE.resolution}</label>
            <select
              id={`${id}-resolution`}
              value={saisie.resolution}
              onChange={(e) => onChanger({ resolution: e.target.value })}
            >
              {options.resolutions.map((resolution) => (
                <option key={resolution} value={resolution}>
                  {texteResolution(resolution)}
                </option>
              ))}
            </select>
            <Origine valeur={origine.valeurs ? texteResolution(origine.valeurs.resolution) : "—"} />
            {statut("resolution")}
          </div>
          {nombre("images_par_seconde")}
          {nombre("debit_max")}
        </>
      )}
    </section>
  );
}

function texteNombre(valeur: number | null): string {
  return valeur === null ? "—" : String(valeur);
}

function Origine({ valeur }: Readonly<{ valeur: string }>) {
  return <span className="origine">d'origine : {valeur}</span>;
}

const STATUTS: Record<ChampModifie["statut"], string> = { pris: "pris", pas_pris: "pas pris", refuse: "refusé" };

/** Statut d'un champ envoyé, avec la valeur demandée et celle relue sur la caméra ; rien s'il n'a pas été envoyé. */
function StatutChamp({
  resultat,
  libelle,
}: Readonly<{ resultat: ChampModifie | undefined; libelle: string }>) {
  if (!resultat) return null;
  const { champ, demande, relu, statut } = resultat;
  if (resultat.raison === "sans_reponse") {
    return (
      <span role="status" aria-label={`Statut : ${libelle}`} className="statut statut-pas_pris">
        pas pris — la caméra n'a pas répondu après l'envoi
      </span>
    );
  }
  return (
    <span role="status" aria-label={`Statut : ${libelle}`} className={`statut statut-${statut}`}>
      {STATUTS[statut]} (demandé : {texteValeur(champ, demande)}, relu : {texteValeur(champ, relu)})
    </span>
  );
}

function texteValeur(champ: string, valeur: ChampModifie["relu"]): string {
  if (valeur === null) return "—";
  if (typeof valeur === "boolean") return valeur ? "affichée" : "cachée";
  if (typeof valeur === "number") return String(valeur);
  if (champ === "image.infrarouge") return INFRAROUGE[valeur as ModeInfrarouge];
  if (champ === "image.contre_jour" || champ === "image.wdr") return COMPENSATION[valeur as ModeCompensation];
  if (champ === "encodage.resolution") return texteResolution(valeur);
  return champ.endsWith(".position") ? textePosition(valeur as Position) : valeur;
}
