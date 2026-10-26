import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router";
import { CircleAlert } from "lucide-react";

import logoComplet from "@/assets/logo-complet.png";
import { useTitreOnglet } from "@/components/EnTeteDePage";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { VERSION_ARGOS } from "@/version";
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
  useTitreOnglet("Connexion");

  if (session.etat === "connecte") {
    const depuis = (location.state as { depuis?: string } | null)?.depuis;
    return <Navigate to={depuis ?? "/live"} replace />;
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
    <div className="flex min-h-svh flex-col items-center justify-center gap-8 px-4 py-10">
      <main className="flex w-full flex-col items-center gap-8">
        <img src={logoComplet} alt="ArgOS" className="w-64 max-w-full" />
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle>
              <h1 className="text-base">Connexion au Site</h1>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={envoyer} className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="identifiant">Identifiant</Label>
                <Input
                  id="identifiant"
                  name="identifiant"
                  autoComplete="username"
                  required
                  value={identifiant}
                  onChange={(e) => setIdentifiant(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="mot_de_passe">Mot de passe</Label>
                <Input
                  id="mot_de_passe"
                  name="mot_de_passe"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={motDePasse}
                  onChange={(e) => setMotDePasse(e.target.value)}
                />
              </div>
              {erreur && (
                <Alert variant="destructive">
                  <CircleAlert />
                  <AlertDescription>{erreur}</AlertDescription>
                </Alert>
              )}
              <Button type="submit" disabled={envoi} className="w-full">
                Se connecter
              </Button>
            </form>
          </CardContent>
        </Card>
      </main>
      <footer className="font-mono text-xs text-muted-foreground">ArgOS {VERSION_ARGOS}</footer>
    </div>
  );
}
