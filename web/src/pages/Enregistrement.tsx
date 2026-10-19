import { useCallback, useEffect, useState, type FormEvent } from "react";

import { messageEchec } from "../cameras";
import { RelectureCamera } from "../RelectureCamera";
import {
  CONSERVATION_MAX,
  CONSERVATION_MIN,
  MO,
  SEUIL_MIN_O,
  formaterDebit,
  formaterDuree,
  formaterOctets,
  libelleEtatEnregistrement,
  libelleSourceDebit,
  libelleTenue,
  lireDebitsEcriture,
  lireEspaceEnregistrements,
  lireReglagesSite,
  modifierReglagesSite,
  type DebitCamera,
  type DebitsEcriture,
  type EspaceEnregistrements,
} from "../reglagesSite";

export function Enregistrement() {
  const [conservation, setConservation] = useState<number | null>(null);
  const [saisieConservation, setSaisieConservation] = useState("");
  const [seuilO, setSeuilO] = useState<number | null>(null);
  const [saisieSeuilMo, setSaisieSeuilMo] = useState("");
  const [espace, setEspace] = useState<EspaceEnregistrements | null>(null);
  const [debits, setDebits] = useState<DebitsEcriture | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  const [selectionnee, setSelectionnee] = useState<DebitCamera | null>(null);

  const rafraichir = useCallback(async () => {
    try {
      const [reglages, espaceLu, debitsLus] = await Promise.all([
        lireReglagesSite(),
        lireEspaceEnregistrements(),
        lireDebitsEcriture(),
      ]);
      setConservation(reglages.conservation_h);
      setSaisieConservation(String(reglages.conservation_h));
      setSeuilO(reglages.seuil_octets_libres);
      setSaisieSeuilMo(String(Math.round(reglages.seuil_octets_libres / MO)));
      setEspace(espaceLu);
      setDebits(debitsLus);
      setErreur(null);
    } catch (e) {
      setErreur(messageEchec(e));
    }
  }, []);

  useEffect(() => {
    void rafraichir();
  }, [rafraichir]);

  async function enregistrerConservation(event: FormEvent) {
    event.preventDefault();
    const heures = Number(saisieConservation);
    if (!Number.isInteger(heures) || heures < CONSERVATION_MIN || heures > CONSERVATION_MAX) {
      setErreur(`La conservation doit être un entier entre ${CONSERVATION_MIN} et ${CONSERVATION_MAX} heures.`);
      return;
    }
    setEnCours(true);
    try {
      const reglages = await modifierReglagesSite({ conservation_h: heures });
      setConservation(reglages.conservation_h);
      setSaisieConservation(String(reglages.conservation_h));
      setDebits(await lireDebitsEcriture());
      setErreur(null);
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnCours(false);
    }
  }

  async function enregistrerSeuil(event: FormEvent) {
    event.preventDefault();
    const mo = Number(saisieSeuilMo);
    if (!Number.isInteger(mo) || mo * MO < SEUIL_MIN_O) {
      setErreur(`Le seuil doit être un entier d’au moins ${Math.round(SEUIL_MIN_O / MO)} Mo.`);
      return;
    }
    setEnCours(true);
    try {
      const reglages = await modifierReglagesSite({ seuil_octets_libres: mo * MO });
      setSeuilO(reglages.seuil_octets_libres);
      setSaisieSeuilMo(String(Math.round(reglages.seuil_octets_libres / MO)));
      const [espaceLu, debitsLus] = await Promise.all([lireEspaceEnregistrements(), lireDebitsEcriture()]);
      setEspace(espaceLu);
      setDebits(debitsLus);
      setErreur(null);
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnCours(false);
    }
  }

  const conservationInchangee = conservation !== null && saisieConservation === String(conservation);
  const seuilInchange =
    seuilO !== null && saisieSeuilMo === String(Math.round(seuilO / MO));
  // Même couple libre / seuil que l’écran affiche (évite un décalage avec `espace.sous_seuil` seul).
  const sousSeuil = espace !== null && seuilO !== null && espace.libre_o < seuilO;

  return (
    <section className="enregistrement-site">
      <h1>Enregistrement</h1>
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
      {sousSeuil && (
        <p className="signal-seuil" role="status">
          Place libre sous le seuil : l’enregistrement continue, agissez si besoin (réduire la
          conservation ou couper des caméras).
        </p>
      )}
      {espace && (
        <dl className="espace-volume">
          <div>
            <dt>Total</dt>
            <dd>{formaterOctets(espace.total_o)}</dd>
          </div>
          <div>
            <dt>Libre</dt>
            <dd>{formaterOctets(espace.libre_o)}</dd>
          </div>
          <div>
            <dt>Utilisé</dt>
            <dd>{formaterOctets(espace.utilise_o)}</dd>
          </div>
        </dl>
      )}
      {debits && (
        <section className="debits-ecriture" aria-labelledby="titre-debits">
          <h2 id="titre-debits">Débits d’écriture</h2>
          <dl className="agregats-debit">
            <div>
              <dt>Débit (enregistrement en cours)</dt>
              <dd>{formaterDebit(debits.debit_enregistrement_o_s)}</dd>
              <dd className={classeTenue(debits.tenue_enregistrement_ok)}>
                Tenue estimée : {formaterDuree(debits.tenue_enregistrement_s)} —{" "}
                {libelleTenue(debits.tenue_enregistrement_ok)}
              </dd>
            </div>
            <div>
              <dt>Projection (toutes Caméras actives)</dt>
              <dd>{formaterDebit(debits.debit_projection_o_s)}</dd>
              <dd className={classeTenue(debits.tenue_projection_ok)}>
                Tenue estimée : {formaterDuree(debits.tenue_projection_s)} —{" "}
                {libelleTenue(debits.tenue_projection_ok)}
              </dd>
            </div>
          </dl>
          <table className="resume-cameras" aria-label="Débits par Caméra">
            <thead>
              <tr>
                <th scope="col">Caméra</th>
                <th scope="col">État</th>
                <th scope="col">Débit</th>
              </tr>
            </thead>
            <tbody>
              {debits.cameras.map((camera) => (
                <tr
                  key={camera.id}
                  className="selectionnable"
                  aria-selected={camera.id === selectionnee?.id}
                  tabIndex={0}
                  onClick={() => setSelectionnee(camera)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      setSelectionnee(camera);
                    }
                  }}
                >
                  <td>{camera.nom}</td>
                  <td>{libelleEtatEnregistrement(camera.etat_enregistrement)}</td>
                  <td>
                    {formaterDebit(camera.debit_o_s)}
                    {camera.source_debit !== "inconnu" && (
                      <span className="source-debit"> ({libelleSourceDebit(camera.source_debit)})</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <form className="conservation" onSubmit={(e) => void enregistrerConservation(e)}>
        <label>
          Conservation (heures)
          <input
            type="number"
            name="conservation_h"
            min={CONSERVATION_MIN}
            max={CONSERVATION_MAX}
            step={1}
            value={saisieConservation}
            onChange={(e) => setSaisieConservation(e.target.value)}
            disabled={conservation === null}
            aria-describedby="aide-conservation"
          />
        </label>
        <p id="aide-conservation" className="aide">
          Durée pendant laquelle le Site garde les segments (de {CONSERVATION_MIN} à {CONSERVATION_MAX} h).
          L’interrupteur d’enregistrement de chaque Caméra reste dans Administration.
        </p>
        <button type="submit" disabled={conservation === null || conservationInchangee || enCours}>
          Enregistrer la conservation
        </button>
      </form>
      <form className="seuil-place" onSubmit={(e) => void enregistrerSeuil(e)}>
        <label>
          Seuil de place disque (Mo)
          <input
            type="number"
            name="seuil_mo"
            min={Math.round(SEUIL_MIN_O / MO)}
            step={1}
            value={saisieSeuilMo}
            onChange={(e) => setSaisieSeuilMo(e.target.value)}
            disabled={seuilO === null}
            aria-describedby="aide-seuil"
          />
        </label>
        <p id="aide-seuil" className="aide">
          Marge d’octets libres sous laquelle un signal apparaît (plancher {Math.round(SEUIL_MIN_O / MO)}{" "}
          Mo, défaut 1024 Mo). Aucune coupure automatique.
        </p>
        <button type="submit" disabled={seuilO === null || seuilInchange || enCours}>
          Enregistrer le seuil
        </button>
      </form>
      {selectionnee ? (
        <RelectureCamera key={selectionnee.id} idCamera={selectionnee.id} nom={selectionnee.nom} />
      ) : (
        debits && (
          <p className="aide invite-relecture">Cliquez sur une Caméra du résumé pour relire ses enregistrements.</p>
        )
      )}
    </section>
  );
}

function classeTenue(ok: boolean | null): string {
  if (ok === true) return "tenue-ok";
  if (ok === false) return "tenue-ambitieuse";
  return "tenue-inconnue";
}
