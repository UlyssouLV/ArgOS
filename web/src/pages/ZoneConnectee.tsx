import { useEffect, useState, type ComponentType } from "react";
import { Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { Camera, Clock, HardDrive, History, LogOut, UserRound, Video } from "lucide-react";

import logoTete from "@/assets/logo-tete.png";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Toaster } from "@/components/ui/sonner";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { VERSION_ARGOS } from "@/version";
import { lireEspaceEnregistrements } from "../reglagesSite";
import { useSession } from "../session";

/** Entrée du rail : icône seule sous 1024 px (libellé en infobulle), libellé à côté au-delà. */
function EntreeRail({
  vers,
  icone: Icone,
  libelle,
  pastille,
}: Readonly<{ vers: string; icone: ComponentType<{ className?: string }>; libelle: string; pastille?: boolean }>) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        {/* Classe en chaîne : le Slot de l'infobulle ne sait pas fusionner la fonction className de NavLink.
            L'entrée active porte aria-current="page" (NavLink). */}
        <NavLink
          to={vers}
          className={cn(
            "relative flex h-10 items-center gap-3 rounded-md px-3 text-muted-foreground outline-none hover:bg-accent hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring max-lg:justify-center",
            "aria-[current=page]:bg-accent aria-[current=page]:text-foreground aria-[current=page]:[&>svg]:text-brand",
            "aria-[current=page]:before:absolute aria-[current=page]:before:inset-y-2 aria-[current=page]:before:left-0 aria-[current=page]:before:w-0.5 aria-[current=page]:before:rounded-full aria-[current=page]:before:bg-brand",
          )}
        >
          <Icone className="size-4 shrink-0" />
          <span className="max-lg:sr-only">{libelle}</span>
          {pastille && (
            <span
              role="img"
              aria-label="Place libre sous le seuil"
              title="Place libre sous le seuil"
              className="size-2 shrink-0 rounded-full bg-destructive max-lg:absolute max-lg:top-2 max-lg:right-2 lg:ml-auto"
            />
          )}
        </NavLink>
      </TooltipTrigger>
      <TooltipContent side="right" className="lg:hidden">
        {libelle}
      </TooltipContent>
    </Tooltip>
  );
}

/** Pages réservées à l'Administrateur connecté : sans session, renvoi sur la connexion puis retour ici. */
export function ZoneConnectee() {
  const session = useSession();
  const location = useLocation();
  const navigate = useNavigate();
  const [sousSeuil, setSousSeuil] = useState(false);

  useEffect(() => {
    if (session.etat !== "connecte") return;
    let annule = false;
    void lireEspaceEnregistrements()
      .then((espace) => {
        if (!annule) setSousSeuil(espace.sous_seuil);
      })
      .catch(() => {
        if (!annule) setSousSeuil(false);
      });
    return () => {
      annule = true;
    };
  }, [session.etat, location.pathname]);

  if (session.etat === "verification") {
    return (
      <div className="flex min-h-svh" aria-busy="true">
        <Skeleton className="w-16 rounded-none lg:w-60" />
        <div className="flex-1 space-y-4 p-6">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    );
  }
  if (session.etat === "deconnecte") {
    return <Navigate to="/connexion" replace state={{ depuis: location.pathname + location.search }} />;
  }

  async function deconnecter() {
    await session.seDeconnecter();
    navigate("/connexion", { replace: true });
  }

  return (
    <TooltipProvider>
      <div className="flex min-h-svh">
        <aside className="sticky top-0 flex h-svh w-16 shrink-0 flex-col border-r bg-card lg:w-60">
          <div className="flex h-16 items-center gap-2 px-3 max-lg:justify-center lg:px-4">
            <img src={logoTete} alt="" className="h-8 w-auto" />
            <span className="text-base font-semibold max-lg:sr-only">ArgOS</span>
          </div>
          <nav aria-label="Navigation" className="flex flex-1 flex-col gap-1 overflow-y-auto px-2 py-2">
            <EntreeRail vers="/live" icone={Video} libelle="Live" />
            <EntreeRail vers="/enregistrement" icone={HardDrive} libelle="Enregistrement" pastille={sousSeuil} />
            <EntreeRail vers="/relecture" icone={History} libelle="Relecture" />
            <div role="group" aria-labelledby="groupe-administration" className="mt-4 flex flex-col gap-1">
              <p
                id="groupe-administration"
                className="px-3 pb-1 text-xs font-medium text-muted-foreground uppercase max-lg:sr-only"
              >
                Administration
              </p>
              <EntreeRail vers="/administration/cameras" icone={Camera} libelle="Caméras" />
              <EntreeRail vers="/administration/heure-du-site" icone={Clock} libelle="Heure du Site" />
            </div>
          </nav>
          <div className="flex flex-col gap-2 border-t p-2 lg:p-3">
            <div className="flex items-center gap-2 max-lg:flex-col">
              <UserRound className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate text-13 max-lg:sr-only">{session.identifiant}</span>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label="Déconnexion" onClick={() => void deconnecter()}>
                    <LogOut />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">Déconnexion</TooltipContent>
              </Tooltip>
            </div>
            <p className="truncate text-center font-mono text-xs text-muted-foreground lg:text-left">
              <span className="max-lg:sr-only">ArgOS </span>
              {VERSION_ARGOS}
            </p>
          </div>
        </aside>
        <main className="flex min-w-0 flex-1 flex-col">
          <Outlet />
        </main>
      </div>
      <Toaster />
    </TooltipProvider>
  );
}
