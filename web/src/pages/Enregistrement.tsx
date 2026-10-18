import { useCallback, useEffect, useState, type FormEvent } from "react";

import { messageEchec } from "../cameras";
import {
  CONSERVATION_MAX,
  CONSERVATION_MIN,
  lireReglagesSite,
  modifierReglagesSite,
} from "../reglagesSite";

export function Enregistrement() {
  const [conservation, setConservation] = useState<number | null>(null);
  const [saisie, setSaisie] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [enregistrement, setEnregistrement] = useState(false);

  const rafraichir = useCallback(async () => {
    try {
      const reglages = await lireReglagesSite();
      setConservation(reglages.conservation_h);
      setSaisie(String(reglages.conservation_h));
      setErreur(null);
    } catch (e) {
      setErreur(messageEchec(e));
    }
  }, []);

  useEffect(() => {
    void rafraichir();
  }, [rafraichir]);

  async function enregistrer(event: FormEvent) {
    event.preventDefault();
    const heures = Number(saisie);
    if (!Number.isInteger(heures) || heures < CONSERVATION_MIN || heures > CONSERVATION_MAX) {
      setErreur(`La conservation doit être un entier entre ${CONSERVATION_MIN} et ${CONSERVATION_MAX} heures.`);
      return;
    }
    setEnregistrement(true);
    try {
      const reglages = await modifierReglagesSite(heures);
      setConservation(reglages.conservation_h);
      setSaisie(String(reglages.conservation_h));
      setErreur(null);
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnregistrement(false);
    }
  }

  const inchange = conservation !== null && saisie === String(conservation);

  return (
    <section className="enregistrement-site">
      <h1>Enregistrement</h1>
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
      <form className="conservation" onSubmit={(e) => void enregistrer(e)}>
        <label>
          Conservation (heures)
          <input
            type="number"
            name="conservation_h"
            min={CONSERVATION_MIN}
            max={CONSERVATION_MAX}
            step={1}
            value={saisie}
            onChange={(e) => setSaisie(e.target.value)}
            disabled={conservation === null}
            aria-describedby="aide-conservation"
          />
        </label>
        <p id="aide-conservation" className="aide">
          Durée pendant laquelle le Site garde les segments (de {CONSERVATION_MIN} à {CONSERVATION_MAX} h).
          L’interrupteur d’enregistrement de chaque Caméra reste dans Administration.
        </p>
        <button type="submit" disabled={conservation === null || inchange || enregistrement}>
          Enregistrer
        </button>
      </form>
    </section>
  );
}
