import { useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router";
import { CircleAlert, VideoOff } from "lucide-react";

import { EnTeteDePage } from "@/components/EnTeteDePage";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { listerCameras, messageEchec, type Camera } from "../cameras";
import { derniereCameraRelue, retenirCameraRelue } from "../relecture";
import { RelectureCamera } from "../RelectureCamera";

/**
 * Relecture d'une Caméra (`/relecture/:idCamera`), un jour à la fois (ADR 0017). `/relecture` seule rouvre la
 * dernière Caméra relue sur ce navigateur, sinon la première.
 */
export function Relecture() {
  const { idCamera } = useParams();
  const [cameras, setCameras] = useState<Camera[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  // Jour choisi, gardé d'une Caméra à l'autre ; `null` : le jour courant du Site.
  const [jour, setJour] = useState<string | null>(null);

  useEffect(() => {
    let annule = false;
    listerCameras()
      .then((liste) => {
        if (!annule) setCameras([...liste].sort((a, b) => a.nom.localeCompare(b.nom, "fr")));
      })
      .catch((e: unknown) => {
        if (!annule) setErreur(messageEchec(e));
      });
    return () => {
      annule = true;
    };
  }, []);

  const selectionnee = cameras?.find((camera) => String(camera.id) === idCamera);

  useEffect(() => {
    if (selectionnee) retenirCameraRelue(selectionnee.id);
  }, [selectionnee]);

  if (idCamera === undefined && cameras?.length) {
    const derniere = cameras.find((camera) => camera.id === derniereCameraRelue()) ?? cameras[0];
    return <Navigate to={`/relecture/${derniere.id}`} replace />;
  }
  if (selectionnee && cameras) {
    return <RelectureCamera key={selectionnee.id} camera={selectionnee} cameras={cameras} jour={jour} onJour={setJour} />;
  }

  return (
    <>
      <EnTeteDePage titre="Relecture" />
      <div className="flex flex-col gap-4 p-6">
        {erreur && (
          <Alert variant="destructive">
            <CircleAlert />
            <AlertDescription>{erreur}</AlertDescription>
          </Alert>
        )}
        {cameras === null && !erreur && <Skeleton className="aspect-video max-h-[60vh] w-full" aria-busy="true" />}
        {cameras !== null && (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-center">
            <VideoOff className="size-8 text-muted-foreground" aria-hidden="true" />
            <p className="font-medium">{cameras.length === 0 ? "Aucune Caméra à relire." : "Caméra inconnue."}</p>
            <p className="text-muted-foreground">
              {cameras.length === 0 ? "En ajouter dans " : "Choisir une Caméra dans "}
              <Link
                to={cameras.length === 0 ? "/administration/cameras" : "/relecture"}
                className="text-foreground underline underline-offset-4"
              >
                {cameras.length === 0 ? "Administration" : "Relecture"}
              </Link>
              .
            </p>
          </div>
        )}
      </div>
    </>
  );
}
