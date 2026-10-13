import { useEffect, useState } from "react";

import { messageEchec, type Camera } from "../cameras";
import {
  lireReglages,
  texteDateHeure,
  texteEcart,
  texteFuseau,
  textePosition,
  type Horloge,
  type Reglages,
} from "../reglages";

type Props = Readonly<{ camera: Camera; onFermer: () => void }>;

/** Réglages de la Caméra lus sur la caméra par ONVIF à l'ouverture, en lecture seule. */
export function ReglagesCamera({ camera, onFermer }: Props) {
  const [reglages, setReglages] = useState<Reglages | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  useEffect(() => {
    let ouvert = true;
    lireReglages(camera.id).then(
      (lus) => ouvert && setReglages(lus),
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
      {!reglages && !erreur && <p>Lecture de la caméra…</p>}
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
      {reglages && (
        <div className="reglages-valeurs">
          <HorlogeLue horloge={reglages.horloge} />
          <section aria-label="Incrustations">
            <h4>Incrustations</h4>
            <dl>
              <dt>Nom</dt>
              <dd>{reglages.incrustations.nom.affichee ? reglages.incrustations.nom.texte : "cachée"}</dd>
              {reglages.incrustations.nom.affichee && (
                <>
                  <dt>Position du nom</dt>
                  <dd>{textePosition(reglages.incrustations.nom.position)}</dd>
                </>
              )}
              <dt>Date et heure</dt>
              <dd>{reglages.incrustations.date_heure.affichee ? "affichée" : "cachée"}</dd>
              {reglages.incrustations.date_heure.affichee && (
                <>
                  <dt>Format</dt>
                  <dd>{reglages.incrustations.date_heure.format ?? "—"}</dd>
                  <dt>Position de la date et heure</dt>
                  <dd>{textePosition(reglages.incrustations.date_heure.position)}</dd>
                </>
              )}
            </dl>
          </section>
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
