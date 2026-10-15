import { useEffect, useId, useState } from "react";

import { LONGUEUR_MOT_DE_PASSE_SUR, messageEchec, type Camera } from "../cameras";
import {
  accepterEnClair,
  COINS,
  empreinteCourte,
  empreinteGroupee,
  estVide,
  faireConfiance,
  fuseauLu,
  lireFuseaux,
  lireReglages,
  mettreALHeure,
  modificationsEntre,
  modifierReglages,
  oublierCertificat,
  RefusOnvif,
  saisieDepuis,
  texteDateHeure,
  texteEcart,
  textePosition,
  type CertificatsCompares,
  type ChampModifie,
  type CleIncrustation,
  type Horloge,
  type IncrustationSaisie,
  type Position,
  type Reglages,
  type ReglagesLus,
  type Saisie,
  type SecuriteOnvif,
} from "../reglages";

type Props = Readonly<{ camera: Camera; onFermer: () => void }>;

/**
 * Réglages de la Caméra lus sur la caméra par ONVIF à l'ouverture ; fuseau, heure et Incrustations se règlent.
 * Un certificat changé, un HTTPS disparu ou une caméra sans HTTPS (ONVIF en clair non accepté) bloque les Réglages
 * jusqu'à la décision de l'Administrateur, puis relit.
 */
export function ReglagesCamera({ camera, onFermer }: Props) {
  const [lus, setLus] = useState<{ origine: ReglagesLus; fuseaux: string[] } | null>(null);
  const [echec, setEchec] = useState<unknown>(null);
  // Incrémentée après une décision sur le certificat ou l'ONVIF en clair : relit la caméra.
  const [lecture, setLecture] = useState(0);

  useEffect(() => {
    let ouvert = true;
    Promise.all([lireReglages(camera.id), lireFuseaux()]).then(
      ([origine, fuseaux]) => ouvert && setLus({ origine, fuseaux }),
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
    <section className="reglages" aria-label={`Réglages de ${camera.nom}`}>
      <div className="reglages-en-tete">
        <h3>Réglages de {camera.nom}</h3>
        <button type="button" onClick={onFermer}>
          Fermer
        </button>
      </div>
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
      {lus && <BandeauSecurite camera={camera} securite={lus.origine.securite} onDecide={relire} />}
      {lus && <FormulaireReglages camera={camera} origine={lus.origine} fuseaux={lus.fuseaux} />}
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

type PropsFormulaire = Readonly<{ camera: Camera; origine: Reglages; fuseaux: string[] }>;

/**
 * Formulaire des Réglages (fuseau, Incrustations) : « Enregistrer » n'envoie que ce qui diffère de la caméra, puis
 * montre le statut de chaque champ envoyé ; « Annuler » revient aux valeurs d'origine, lues à l'ouverture et
 * toujours affichées. La mise à l'heure du Site part seule, à la demande.
 */
function FormulaireReglages({ camera, origine, fuseaux }: PropsFormulaire) {
  // Dernières valeurs lues sur la caméra : à l'ouverture, puis relues après chaque envoi.
  const [actuels, setActuels] = useState(origine);
  const [saisie, setSaisie] = useState<Saisie>(() => saisieDepuis(origine));
  const [statuts, setStatuts] = useState<Record<string, ChampModifie>>({});
  const [aCacher, setACacher] = useState<CleIncrustation | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const modification = modificationsEntre(actuels, saisie);

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
        void enregistrer();
      }}
    >
      <div className="reglages-valeurs">
        <ChampsHorloge
          camera={camera}
          origine={origine}
          actuels={actuels}
          fuseau={saisie.fuseau}
          fuseaux={fuseaux}
          statuts={statuts}
          onFuseau={(fuseau) => setSaisie((avant) => ({ ...avant, fuseau }))}
          onHorloge={(horloge) => setActuels((avant) => ({ ...avant, horloge }))}
        />
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
      </div>
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
      <div className="reglages-actions">
        <button type="submit" disabled={envoi || estVide(modification)}>
          {envoi ? "Envoi à la caméra…" : "Enregistrer"}
        </button>
        <button
          type="button"
          disabled={envoi}
          onClick={() => {
            setSaisie(saisieDepuis(origine));
            setACacher(null);
            setStatuts({});
          }}
        >
          Annuler
        </button>
      </div>
    </form>
  );
}

type PropsHorloge = Readonly<{
  camera: Camera;
  origine: Reglages;
  actuels: Reglages;
  fuseau: string;
  fuseaux: string[];
  statuts: Record<string, ChampModifie>;
  onFuseau: (fuseau: string) => void;
  onHorloge: (horloge: Horloge) => void;
}>;

/**
 * Horloge relue sur la caméra (après un envoi ou une mise à l'heure), fuseau à choisir, et mise à l'heure du Site :
 * confirmée quand la caméra se règle sur un serveur de temps, car elle coupe cette synchronisation.
 */
function ChampsHorloge({ camera, origine, actuels, fuseau, fuseaux, statuts, onFuseau, onHorloge }: PropsHorloge) {
  const id = useId();
  const horloge = actuels.horloge;
  const [confirmation, setConfirmation] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [faite, setFaite] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const fuseauOrigine = fuseauLu(origine.horloge);

  async function mettre() {
    setConfirmation(false);
    setEnvoi(true);
    setErreur(null);
    try {
      onHorloge(await mettreALHeure(camera.id));
      setFaite(true);
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <section aria-label="Horloge">
      <h4>Horloge</h4>
      <dl>
        <dt>Date et heure de la caméra (UTC)</dt>
        <dd>{texteDateHeure(horloge.date_heure_utc)}</dd>
        <dt>Écart avec le Site</dt>
        <dd>{texteEcart(horloge.ecart_s)}</dd>
        <dt>Serveur de temps (NTP)</dt>
        <dd>
          {horloge.mode === "ntp" ? "utilisé" : "non utilisé"}
          {horloge.serveur_ntp && ` (serveur : ${horloge.serveur_ntp})`}
        </dd>
      </dl>
      <fieldset>
        <legend>Fuseau et heure</legend>
        <label htmlFor={`${id}-fuseau`}>Fuseau</label>
        <select id={`${id}-fuseau`} value={fuseau} onChange={(e) => onFuseau(e.target.value)}>
          {/* Fuseau que la caméra a et qu'ArgOS ne reconnaît pas : montré tel quel tant qu'il n'est pas changé. */}
          {!fuseaux.includes(fuseau) && <option value={fuseau}>{fuseau || "—"}</option>}
          {fuseaux.map((nom) => (
            <option key={nom} value={nom}>
              {nom}
            </option>
          ))}
        </select>
        <Origine valeur={fuseauOrigine || "—"} />
        <StatutChamp resultat={statuts["horloge.fuseau"]} libelle="fuseau" />
        <button
          type="button"
          disabled={envoi}
          onClick={() => (horloge.mode === "ntp" ? setConfirmation(true) : void mettre())}
        >
          {envoi ? "Mise à l'heure…" : "Mettre à l'heure du Site"}
        </button>
        {confirmation && (
          <p className="confirmation">
            <span>
              {horloge.serveur_ntp
                ? `La caméra se règle sur le serveur de temps ${horloge.serveur_ntp}.`
                : "La caméra se règle sur un serveur de temps."}{" "}
              La mettre à l'heure du Site coupe cette synchronisation.
            </span>
            <button type="button" className="danger" onClick={() => void mettre()}>
              Mettre à l'heure quand même
            </button>
            <button type="button" onClick={() => setConfirmation(false)}>
              Garder le serveur de temps
            </button>
          </p>
        )}
        {faite && !envoi && (
          <span role="status" aria-label="Statut : mise à l'heure" className="statut">
            écart relu : {texteEcart(horloge.ecart_s)}
          </span>
        )}
        {erreur && (
          <p className="erreur" role="alert">
            {erreur}
          </p>
        )}
      </fieldset>
    </section>
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
  return (
    <span role="status" aria-label={`Statut : ${libelle}`} className={`statut statut-${statut}`}>
      {STATUTS[statut]} (demandé : {texteValeur(champ, demande)}, relu : {texteValeur(champ, relu)})
    </span>
  );
}

function texteValeur(champ: string, valeur: ChampModifie["relu"]): string {
  if (valeur === null) return "—";
  if (typeof valeur === "boolean") return valeur ? "affichée" : "cachée";
  return champ.endsWith(".position") ? textePosition(valeur as Position) : valeur;
}
