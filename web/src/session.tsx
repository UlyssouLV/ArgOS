import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { appeler, requete, surNonConnecte } from "./api";

type EtatSession =
  | { etat: "verification" }
  | { etat: "connecte"; identifiant: string }
  | { etat: "deconnecte" };

export type ResultatConnexion = "ok" | "refuse" | "trop-de-tentatives" | "injoignable";

type Session = EtatSession & {
  seConnecter: (identifiant: string, motDePasse: string) => Promise<ResultatConnexion>;
  seDeconnecter: () => Promise<void>;
};

const ContexteSession = createContext<Session | null>(null);

async function lireMoi(): Promise<EtatSession> {
  try {
    const reponse = await appeler("/api/moi");
    if (!reponse.ok) return { etat: "deconnecte" };
    const { identifiant } = (await reponse.json()) as { identifiant: string };
    return { etat: "connecte", identifiant };
  } catch {
    // NonConnecte (401) ou API injoignable : la page de connexion le dira à la prochaine tentative.
    return { etat: "deconnecte" };
  }
}

export function FournisseurSession({ children }: { children: ReactNode }) {
  const [etat, setEtat] = useState<EtatSession>({ etat: "verification" });

  useEffect(() => {
    surNonConnecte(() => setEtat({ etat: "deconnecte" }));
    lireMoi().then(setEtat);
  }, []);

  const seConnecter = useCallback(async (identifiant: string, motDePasse: string) => {
    let reponse: Response;
    try {
      reponse = await requete("/api/session", {
        method: "POST",
        body: JSON.stringify({ identifiant, mot_de_passe: motDePasse }),
      });
    } catch {
      return "injoignable";
    }
    if (reponse.status === 429) return "trop-de-tentatives";
    if (!reponse.ok) return "refuse";
    setEtat(await lireMoi());
    return "ok";
  }, []);

  const seDeconnecter = useCallback(async () => {
    try {
      await requete("/api/session", { method: "DELETE" });
    } finally {
      setEtat({ etat: "deconnecte" });
    }
  }, []);

  const session = useMemo(() => ({ ...etat, seConnecter, seDeconnecter }), [etat, seConnecter, seDeconnecter]);
  return <ContexteSession.Provider value={session}>{children}</ContexteSession.Provider>;
}

export function useSession(): Session {
  const session = useContext(ContexteSession);
  if (session === null) throw new Error("useSession hors de FournisseurSession");
  return session;
}
