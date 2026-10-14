import { useEffect, useId, useState } from "react";

import { messageEchec, type Camera } from "../cameras";
import {
  COINS,
  estVide,
  lireReglages,
  modificationsEntre,
  modifierReglages,
  saisieDepuis,
  texteDateHeure,
  texteEcart,
  texteFuseau,
  textePosition,
  type ChampModifie,
  type CleIncrustation,
  type Horloge,
  type IncrustationSaisie,
  type Position,
  type Reglages,
  type Saisie,
} from "../reglages";

type Props = Readonly<{ camera: Camera; onFermer: () => void }>;

/** Réglages de la Caméra lus sur la caméra par ONVIF à l'ouverture ; les Incrustations se règlent. */
export function ReglagesCamera({ camera, onFermer }: Props) {
  const [origine, setOrigine] = useState<Reglages | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    let ouvert = true;
    lireReglages(camera.id).then(
      (lus) => ouvert && setOrigine(lus),
      (e: unknown) => ouvert && setErreur(messageEchec(e)),
    );
    return () => {
      ouvert = false;
    };
  }, [camera.id]);

  return (
    <section className="reglages" aria-label={`Réglages de ${camera.nom}`}>
      <div className="reglages-en-tete">
        <h3>Réglages de {camera.nom}</h3>
        <button type="button" onClick={onFermer}>
          Fermer
        </button>
      </div>
      {!origine && !erreur && <p>Lecture de la caméra…</p>}
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
      {origine && (
        <div className="reglages-valeurs">
          <HorlogeLue horloge={origine.horloge} />
          <FormulaireIncrustations camera={camera} origine={origine} />
        </div>
      )}
    </section>
  );
}

function HorlogeLue({ horloge }: Readonly<{ horloge: Horloge }>) {
  return (
    <section aria-label="Horloge">
      <h4>Horloge</h4>
      <dl>
        <dt>Date et heure de la caméra (UTC)</dt>
        <dd>{texteDateHeure(horloge.date_heure_utc)}</dd>
        <dt>Écart avec le Site</dt>
        <dd>{texteEcart(horloge.ecart_s)}</dd>
        <dt>Fuseau</dt>
        <dd>{texteFuseau(horloge)}</dd>
        <dt>Serveur de temps (NTP)</dt>
        <dd>
          {horloge.mode === "ntp" ? "utilisé" : "non utilisé"}
          {horloge.serveur_ntp && ` (serveur : ${horloge.serveur_ntp})`}
        </dd>
      </dl>
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
 * Formulaire des Incrustations : « Enregistrer » n'envoie que ce qui diffère de la caméra, puis montre le statut
 * de chaque champ envoyé ; « Annuler » revient aux valeurs d'origine, lues à l'ouverture et toujours affichées.
 */
function FormulaireIncrustations({ camera, origine }: PropsFormulaire) {
  // Dernières valeurs lues sur la caméra : à l'ouverture, puis relues après chaque envoi.
  const [actuels, setActuels] = useState(origine);
  const [saisie, setSaisie] = useState<Saisie>(() => saisieDepuis(origine));
  const [statuts, setStatuts] = useState<Record<string, ChampModifie>>({});
  const [aCacher, setACacher] = useState<CleIncrustation | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const modification = modificationsEntre(actuels, saisie);

  function changer(cle: CleIncrustation, champs: Partial<IncrustationSaisie>) {
    setSaisie((avant) => ({ ...avant, [cle]: { ...avant[cle], ...champs } }));
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
    <section aria-label="Incrustations">
      <h4>Incrustations</h4>
      <form
        className="reglages-formulaire"
        onSubmit={(e) => {
          e.preventDefault();
          void enregistrer();
        }}
      >
        {(["nom", "date_heure"] as const).map((cle) => (
          <ChampsIncrustation
            key={cle}
            cle={cle}
            origine={origine}
            actuels={actuels}
            saisie={saisie[cle]}
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
            }}
          >
            Annuler
          </button>
        </div>
      </form>
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

/** « pris », « pas pris » avec la valeur que la caméra a gardée, ou « refusé » ; rien si le champ n'a pas été envoyé. */
function StatutChamp({
  resultat,
  libelle,
}: Readonly<{ resultat: ChampModifie | undefined; libelle: string }>) {
  if (!resultat) return null;
  const texte = {
    pris: "pris",
    pas_pris: `pas pris (la caméra a gardé : ${texteValeur(resultat)})`,
    refuse: "refusé",
  }[resultat.statut];
  return (
    <span
      role="status"
      aria-label={`Statut : ${libelle}`}
      className={`statut statut-${resultat.statut}`}
    >
      {texte}
    </span>
  );
}

function texteValeur({ champ, relu }: ChampModifie): string {
  if (relu === null) return "—";
  if (typeof relu === "boolean") return relu ? "affichée" : "cachée";
  return champ.endsWith(".position") ? textePosition(relu as Position) : relu;
}
