import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { ChevronLeft, ChevronRight, CircleAlert, VideoOff } from "lucide-react";

import { EnTeteDePage } from "@/components/EnTeteDePage";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { listerCameras, messageEchec, texteCodec, texteEtat, type Camera, type Etat } from "../cameras";
import { LecteurFlux } from "../LecteurFlux";

const RAFRAICHISSEMENT_MS = 10_000;

type CameraLive = Camera & { chemin_flux: string };

const COULEURS_ETAT: Record<Etat, string> = {
  online: "bg-success",
  offline: "bg-destructive",
  unknown: "bg-unknown",
};

/** Caméras actives, dans l'ordre des noms : l'ordre du tour du Site. */
function camerasActives(cameras: Camera[]): CameraLive[] {
  return cameras
    .filter((camera): camera is CameraLive => camera.active && camera.chemin_flux !== null)
    .sort((a, b) => a.nom.localeCompare(b.nom, "fr"));
}

/** Le focus est dans un champ : les flèches y déplacent le curseur, pas la Caméra. */
function dansUnChamp(cible: EventTarget | null): boolean {
  return (
    cible instanceof HTMLElement &&
    (cible.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(cible.tagName))
  );
}

export function Live() {
  const [actives, setActives] = useState<CameraLive[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [idCourant, setIdCourant] = useState<number | null>(null);

  // Rafraîchit aussi l'état de la Caméra affichée.
  const rafraichir = useCallback(async () => {
    try {
      setActives(camerasActives(await listerCameras()));
      setErreur(null);
    } catch (e) {
      setErreur(messageEchec(e));
    }
  }, []);

  useEffect(() => {
    void rafraichir();
    const minuterie = setInterval(() => void rafraichir(), RAFRAICHISSEMENT_MS);
    return () => clearInterval(minuterie);
  }, [rafraichir]);

  // Une Caméra désactivée entre deux rafraîchissements laisse place à la première.
  const courante = actives?.find((camera) => camera.id === idCourant) ?? actives?.[0] ?? null;
  const rang = actives && courante ? actives.indexOf(courante) : -1;

  /** Avance de `pas` Caméras dans le tour, en boucle. */
  const decaler = useCallback(
    (pas: number) => {
      if (!actives?.length || rang < 0) return;
      setIdCourant(actives[(rang + pas + actives.length) % actives.length].id);
    },
    [actives, rang],
  );

  // Seulement sur le Live : le raccourci part avec la page.
  useEffect(() => {
    function auClavier(evenement: KeyboardEvent) {
      if (evenement.altKey || evenement.ctrlKey || evenement.metaKey || evenement.shiftKey) return;
      if (dansUnChamp(evenement.target)) return;
      if (evenement.key === "ArrowRight") decaler(1);
      else if (evenement.key === "ArrowLeft") decaler(-1);
    }
    window.addEventListener("keydown", auClavier);
    return () => window.removeEventListener("keydown", auClavier);
  }, [decaler]);

  return (
    <>
      <EnTeteDePage titre="Live" />
      <div className="flex min-h-0 flex-1 flex-col">
        {erreur && (
          <Alert variant="destructive" className="m-4 w-auto">
            <CircleAlert />
            <AlertDescription>{erreur}</AlertDescription>
          </Alert>
        )}
        {actives === null && !erreur && <Skeleton className="m-4 min-h-64 flex-1 rounded-lg" aria-busy="true" />}
        {actives?.length === 0 && (
          <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
            <VideoOff className="size-8 text-muted-foreground" aria-hidden="true" />
            <p className="font-medium">Aucune Caméra active.</p>
            <p className="text-muted-foreground">
              En ajouter ou en réactiver dans{" "}
              <Link to="/administration/cameras" className="text-foreground underline underline-offset-4">
                Administration
              </Link>
              .
            </p>
          </div>
        )}
        {courante && actives && (
          <>
            <section
              aria-label="Caméra courante"
              className="flex min-h-11 flex-wrap items-center gap-x-4 gap-y-1 border-b bg-card px-4 py-1.5"
            >
              <div className="flex min-w-0 items-baseline gap-2">
                <h2 className="truncate text-sm font-semibold">{courante.nom}</h2>
                {courante.emplacement && (
                  <span className="truncate text-13 text-muted-foreground">{courante.emplacement}</span>
                )}
              </div>
              <span className="flex items-center gap-1.5 text-13">
                <span className={cn("size-2 rounded-full", COULEURS_ETAT[courante.etat])} aria-hidden="true" />
                {texteEtat(courante.etat)}
              </span>
              <span className="font-mono text-xs text-muted-foreground">{texteCodec(courante.codec)}</span>
              <div className="ml-auto flex items-center gap-1">
                <span className="mr-2 font-mono text-xs text-muted-foreground">
                  {rang + 1} / {actives.length}
                </span>
                <Button variant="outline" size="sm" onClick={() => decaler(-1)} disabled={actives.length < 2}>
                  <ChevronLeft />
                  Précédente
                </Button>
                <Button variant="outline" size="sm" onClick={() => decaler(1)} disabled={actives.length < 2}>
                  Suivante
                  <ChevronRight />
                </Button>
              </div>
            </section>
            {/* Vidéo 16:9 au plus grand dans la zone, sur fond noir. */}
            <div className="relative min-h-64 flex-1 bg-video">
              {/* Une clé par Flux : changer de Caméra démonte le lecteur, qui ferme sa connexion (WebRTC ou HLS). */}
              <LecteurFlux
                key={courante.chemin_flux}
                cheminFlux={courante.chemin_flux}
                codec={courante.codec}
                className="absolute inset-0 aspect-auto [&>p]:text-base"
              />
            </div>
          </>
        )}
      </div>
    </>
  );
}
