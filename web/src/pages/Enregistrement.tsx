import { useCallback, useEffect, useState, type FormEvent } from "react";

import { messageEchec } from "../cameras";
import {
  CONSERVATION_MAX,
  CONSERVATION_MIN,
  MO,
  SEUIL_MIN_O,
  formaterOctets,
  lireEspaceEnregistrements,
  lireReglagesSite,
  modifierReglagesSite,
  type EspaceEnregistrements,
} from "../reglagesSite";

export function Enregistrement() {
  const [conservation, setConservation] = useState<number | null>(null);
  const [saisieConservation, setSaisieConservation] = useState("");
  const [seuilO, setSeuilO] = useState<number | null>(null);
  const [saisieSeuilMo, setSaisieSeuilMo] = useState("");
  const [espace, setEspace] = useState<EspaceEnregistrements | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enregistrement, setEnregistrement] = useState(false);

  const rafraichir = useCallback(async () => {
    try {
      const [reglages, espaceLu] = await Promise.all([lireReglagesSite(), lireEspaceEnregistrements()]);
      setConservation(reglages.conservation_h);
      setSaisieConservation(String(reglages.conservation_h));
      setSeuilO(reglages.seuil_octets_libres);
      setSaisieSeuilMo(String(Math.round(reglages.seuil_octets_libres / MO)));
      setEspace(espaceLu);
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
    setEnregistrement(true);
    try {
      const reglages = await modifierReglagesSite({ conservation_h: heures });
      setConservation(reglages.conservation_h);
      setSaisieConservation(String(reglages.conservation_h));
      setErreur(null);
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnregistrement(false);
    }
  }

  async function enregistrerSeuil(event: FormEvent) {
    event.preventDefault();
    const mo = Number(saisieSeuilMo);
    if (!Number.isInteger(mo) || mo * MO < SEUIL_MIN_O) {
      setErreur(`Le seuil doit être un entier d’au moins ${Math.round(SEUIL_MIN_O / MO)} Mo.`);
      return;
    }
    setEnregistrement(true);
    try {
      const reglages = await modifierReglagesSite({ seuil_octets_libres: mo * MO });
      setSeuilO(reglages.seuil_octets_libres);
      setSaisieSeuilMo(String(Math.round(reglages.seuil_octets_libres / MO)));
      const espaceLu = await lireEspaceEnregistrements();
      setEspace(espaceLu);
      setErreur(null);
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnregistrement(false);
    }
  }

  const conservationInchangee = conservation !== null && saisieConservation === String(conservation);
  const seuilInchange =
    seuilO !== null && saisieSeuilMo === String(Math.round(seuilO / MO));

  return (
    <section className="enregistrement-site">
      <h1>Enregistrement</h1>
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
      {espace?.sous_seuil && (
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
        <button type="submit" disabled={conservation === null || conservationInchangee || enregistrement}>
          Enregistrer la conservation
        </button>
      </form>
      <form className="seuil-place" onSubmit={(e) => void enregistrerSeuil(e)}>
        <label>
          Seuil de place libre (Mo)
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
        <button type="submit" disabled={seuilO === null || seuilInchange || enregistrement}>
          Enregistrer le seuil
        </button>
      </form>
    </section>
  );
}
