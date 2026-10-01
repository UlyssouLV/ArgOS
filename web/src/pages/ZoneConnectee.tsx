import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router";

import { useSession } from "../session";

/** Pages réservées à l'Administrateur connecté : sans session, renvoi sur la connexion puis retour ici. */
export function ZoneConnectee() {
  const session = useSession();
  const location = useLocation();
  const navigate = useNavigate();

  if (session.etat === "verification") return <p className="chargement">Chargement…</p>;
  if (session.etat === "deconnecte") {
    return <Navigate to="/connexion" replace state={{ depuis: location.pathname + location.search }} />;
  }

  async function deconnecter() {
    await session.seDeconnecter();
    navigate("/connexion", { replace: true });
  }

  return (
    <>
      <header className="en-tete">
        <span className="marque">ArgOS</span>
        <nav className="onglets">
          <NavLink to="/administration">Administration</NavLink>
          <NavLink to="/live">Live</NavLink>
        </nav>
        <span className="identifiant">{session.identifiant}</span>
        <button type="button" onClick={deconnecter}>
          Déconnexion
        </button>
      </header>
      <main className="contenu">
        <Outlet />
      </main>
    </>
  );
}
