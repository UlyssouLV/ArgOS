import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";

import { messageEchec } from "../cameras";
import {
  lireHeureDuSite,
  modifierHeureDuSite,
  MOTIF_SERVEUR_NTP,
  texteHeure,
  texteSourceUtilisee,
  type HeureDuSite as Heure,
  type Source,
} from "../heureSite";
import { lireFuseaux } from "../reglages";

// Relecture de ce que sert le Serveur de temps du Site (source utilisée, repli).
const RAFRAICHISSEMENT_MS = 10_000;

/** Page Heure du Site de l'Administration (docs/adr/0014-serveur-de-temps-du-site.md). */
export function HeureDuSite() {
  const [heure, setHeure] = useState<Heure | null>(null);
  // Écart entre l'heure servie et celle du navigateur à la dernière lecture : l'heure affichée avance seule.
  const [ecartMs, setEcartMs] = useState<number | null>(null);
  const [maintenant, setMaintenant] = useState(() => Date.now());
  const [fuseaux, setFuseaux] = useState<string[]>([]);
  const [source, setSource] = useState<Source>("ntp");
  const [serveur, setServeur] = useState("");
  const [fuseau, setFuseau] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);

  const montrer = useCallback((lue: Heure, saisie: boolean) => {
    setHeure(lue);
    setEcartMs(lue.heure === null ? null : Date.parse(lue.heure) - Date.now());
    if (saisie) {
      setSource(lue.source);
      setServeur(lue.serveur_ntp);
      setFuseau(lue.fuseau);
    }
  }, []);

  const rafraichir = useCallback(
    async (saisie: boolean) => {
      try {
        montrer(await lireHeureDuSite(), saisie);
        setErreur(null);
      } catch (e) {
        setErreur(messageEchec(e));
      }
    },
    [montrer],
  );

  useEffect(() => {
    void rafraichir(true);
    void lireFuseaux().then(setFuseaux, (e: unknown) => setErreur(messageEchec(e)));
    const relecture = setInterval(() => void rafraichir(false), RAFRAICHISSEMENT_MS);
    const seconde = setInterval(() => setMaintenant(Date.now()), 1000);
    return () => {
      clearInterval(relecture);
      clearInterval(seconde);
    };
  }, [rafraichir]);

  async function enregistrer(event: FormEvent) {
    event.preventDefault();
    if (heure === null) return;
    setEnCours(true);
    try {
      montrer(
        await modifierHeureDuSite({ source, fuseau, ...(source === "ntp" ? { serveur_ntp: serveur.trim() } : {}) }),
        true,
      );
      setErreur(null);
      setMessage("Heure du Site enregistrée : les Caméras actives sont recalées.");
    } catch (e) {
      setErreur(messageEchec(e));
      setMessage(null);
    } finally {
      setEnCours(false);
    }
  }

  const inchangee =
    heure !== null &&
    source === heure.source &&
    fuseau === heure.fuseau &&
    (source === "horloge_serveur" || serveur.trim() === heure.serveur_ntp);
  // Le fuseau du Site reste proposé même s'il n'est pas parmi les fuseaux courants (celui de l'hôte).
  const fuseauxProposes = heure && !fuseaux.includes(heure.fuseau) ? [heure.fuseau, ...fuseaux] : fuseaux;

  return (
    <section className="heure-du-site">
      <p className="fil">
        <Link to="/administration">Administration</Link> › Heure du Site
      </p>
      <h1>Heure du Site</h1>
      {erreur && (
        <p className="erreur" role="alert">
          {erreur}
        </p>
      )}
      {message && (
        <p className="message" role="status">
          {message}
        </p>
      )}
      {heure && (
        <dl className="etat-heure" aria-label="Heure du Site">
          <div>
            <dt>Heure actuelle du Site</dt>
            <dd>{texteHeure(ecartMs === null ? null : new Date(maintenant + ecartMs), heure.fuseau)}</dd>
          </div>
          <div>
            <dt>Source utilisée</dt>
            <dd>{texteSourceUtilisee(heure)}</dd>
          </div>
          <div>
            <dt>Fuseau</dt>
            <dd>
              {heure.fuseau}
              {heure.fuseau_de_l_hote && " (celui du serveur)"}
            </dd>
          </div>
          <div>
            <dt>Adresse du Serveur de temps</dt>
            <dd>
              {heure.adresse_serveur_de_temps ??
                "inconnue : renseigner l’IP du Site (MTX_WEBRTCADDITIONALHOSTS) ; aucune Caméra n’est calée"}
            </dd>
          </div>
        </dl>
      )}
      <form className="reglage-heure" aria-label="Régler l’Heure du Site" onSubmit={(e) => void enregistrer(e)}>
        <fieldset disabled={heure === null || enCours}>
          <legend>Source de l’heure</legend>
          <label>
            <input
              type="radio"
              name="source"
              checked={source === "ntp"}
              onChange={() => setSource("ntp")}
            />
            Serveur NTP externe
          </label>
          <label className="serveur-ntp">
            Adresse du serveur NTP
            <input
              type="text"
              value={serveur}
              required={source === "ntp"}
              pattern={MOTIF_SERVEUR_NTP}
              disabled={source !== "ntp"}
              onChange={(e) => setServeur(e.target.value)}
            />
          </label>
          <label>
            <input
              type="radio"
              name="source"
              checked={source === "horloge_serveur"}
              onChange={() => setSource("horloge_serveur")}
            />
            Horloge du serveur
          </label>
          <p className="aide">
            Un serveur NTP injoignable laisse le Site servir l’horloge du serveur, jusqu’à ce qu’il réponde.
          </p>
        </fieldset>
        <label>
          Fuseau du Site
          <select value={fuseau} disabled={heure === null || enCours} onChange={(e) => setFuseau(e.target.value)}>
            {fuseauxProposes.map((nom) => (
              <option key={nom} value={nom}>
                {nom}
              </option>
            ))}
          </select>
        </label>
        <p className="aide">
          Enregistrer recale toutes les Caméras actives : serveur NTP = le Site, fuseau = celui du Site.
        </p>
        <button type="submit" disabled={heure === null || inchangee || enCours}>
          Enregistrer
        </button>
      </form>
    </section>
  );
}
