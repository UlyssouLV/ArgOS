import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router";

import { useSession, type ResultatConnexion } from "../session";

const MESSAGES: Record<Exclude<ResultatConnexion, "ok">, string> = {
  // Ne dit jamais lequel des deux est faux.
  refuse: "Identifiant ou mot de passe incorrect.",
  "trop-de-tentatives": "Trop de tentatives, réessayez dans 15 min",
  injoignable: "L'API du Site ne répond pas. Réessayez dans un instant.",
};

export function Connexion() {
  const session = useSession();
  const location = useLocation();
  const [identifiant, setIdentifiant] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  if (session.etat === "connecte") {
    const depuis = (location.state as { depuis?: string } | null)?.depuis;
    return <Navigate to={depuis ?? "/administration"} replace />;
  }

  async function envoyer(evenement: FormEvent) {
    evenement.preventDefault();
    setEnvoi(true);
    setErreur(null);
    const resultat = await session.seConnecter(identifiant, motDePasse);
    setEnvoi(false);
    if (resultat !== "ok") setErreur(MESSAGES[resultat]);
  }

  return (
    <main className="connexion">
      <form onSubmit={envoyer}>
        <h1>ArgOS</h1>
        <label>
          Identifiant
          <input
            name="identifiant"
            autoComplete="username"
            required
            value={identifiant}
            onChange={(e) => setIdentifiant(e.target.value)}
          />
        </label>
        <label>
          Mot de passe
          <input
            name="mot_de_passe"
            type="password"
            autoComplete="current-password"
            required
            value={motDePasse}
            onChange={(e) => setMotDePasse(e.target.value)}
          />
        </label>
        {erreur && (
          <p className="erreur" role="alert">
            {erreur}
          </p>
        )}
        <button type="submit" disabled={envoi}>
          Se connecter
        </button>
      </form>
    </main>
  );
}
