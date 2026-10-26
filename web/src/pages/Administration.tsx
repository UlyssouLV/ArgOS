import { useCallback, useEffect, useState } from "react";
import { CameraOff, Radar, Settings2 } from "lucide-react";

import { EnTeteDePage } from "@/components/EnTeteDePage";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { notifier } from "@/notifier";
import {
  listerCameras,
  messageEchec,
  modifierCamera,
  texteAgeSegment,
  texteCodec,
  texteEtat,
  texteEtatEnregistrement,
  texteMac,
  texteRaison,
  type Camera,
  type Etat,
} from "../cameras";
import { DetecterCameras } from "./DetecterCameras";
import { ReglagesCamera } from "./ReglagesCamera";

const RAFRAICHISSEMENT_MS = 10_000;

const COULEURS_ETAT: Record<Etat, string> = {
  online: "bg-success",
  offline: "bg-destructive",
  unknown: "bg-unknown",
};

const COLONNES = ["Nom", "Adresse", "État", "Flux", "Enregistrement", "Réglages"];

export function Administration() {
  const [cameras, setCameras] = useState<Camera[] | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enReglages, setEnReglages] = useState<number | null>(null);
  const [enDetection, setEnDetection] = useState(false);

  const rafraichir = useCallback(async () => {
    try {
      setCameras(await listerCameras());
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

  /** Interrupteur d'une ligne : résultat en toast, puis la liste est relue. */
  async function changerEnregistrement(camera: Camera, enregistrement: boolean) {
    try {
      await modifierCamera(camera.id, { enregistrement });
      notifier(`Enregistrement de ${camera.nom} ${enregistrement ? "activé" : "arrêté"}.`);
    } catch (e) {
      const message = messageEchec(e);
      if (message) notifier(message, "echec");
    }
    await rafraichir();
  }

  const reglee = cameras?.find((camera) => camera.id === enReglages) ?? null;

  return (
    <>
      <EnTeteDePage
        titre="Caméras"
        surtitre="Administration"
        actions={
          <Button onClick={() => setEnDetection(true)}>
            <Radar />
            Détecter des Caméras
          </Button>
        }
      />
      <div className="flex flex-col gap-6 p-6">
        {erreur && (
          <Alert variant="destructive">
            <AlertDescription>{erreur}</AlertDescription>
          </Alert>
        )}
        {cameras === null && !erreur && <Squelettes />}
        {cameras?.length === 0 && <AucuneCamera onDetecter={() => setEnDetection(true)} />}
        {cameras && cameras.length > 0 && (
          <div className="rounded-lg border bg-card">
            <Table aria-label="Caméras">
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  {COLONNES.map((colonne) => (
                    <TableHead key={colonne} className={cn(colonne === "Réglages" && "text-right")}>
                      {colonne}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {cameras.map((camera) => (
                  <LigneCamera
                    key={camera.id}
                    camera={camera}
                    onEnregistrement={(enregistrement) => void changerEnregistrement(camera, enregistrement)}
                    onReglages={() => setEnReglages(camera.id)}
                  />
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
      <DetecterCameras
        ouverte={enDetection}
        onFermer={() => setEnDetection(false)}
        onCameraAjoutee={() => void rafraichir()}
      />
      {reglee && <ReglagesCamera camera={reglee} onFermer={() => setEnReglages(null)} onModifiee={rafraichir} />}
    </>
  );
}

function Squelettes() {
  return (
    <div className="space-y-2 rounded-lg border bg-card p-4" aria-busy="true" aria-label="Chargement des Caméras">
      {[0, 1, 2].map((rang) => (
        <Skeleton key={rang} className="h-10 w-full" />
      ))}
    </div>
  );
}

/** État vide : icône, phrase et l'action utile, la Détection. */
function AucuneCamera({ onDetecter }: Readonly<{ onDetecter: () => void }>) {
  return (
    <section
      aria-label="Aucune Caméra"
      className="flex flex-col items-center gap-3 rounded-lg border border-dashed bg-card px-6 py-12 text-center"
    >
      <CameraOff className="size-8 text-muted-foreground" aria-hidden="true" />
      <p className="text-base font-semibold">Aucune Caméra</p>
      <p className="text-muted-foreground">Détectez les caméras du réseau pour en ajouter une.</p>
      <Button variant="outline" onClick={onDetecter}>
        Détecter des Caméras
      </Button>
    </section>
  );
}

function LigneCamera({
  camera,
  onEnregistrement,
  onReglages,
}: Readonly<{ camera: Camera; onEnregistrement: (enregistrement: boolean) => void; onReglages: () => void }>) {
  const raison = texteRaison(camera.raison_etat);
  return (
    <TableRow>
      <TableCell>
        <div className="font-medium">{camera.nom}</div>
        {camera.emplacement && <div className="text-13 text-muted-foreground">{camera.emplacement}</div>}
      </TableCell>
      <TableCell className="font-mono text-xs">
        <div>
          {camera.hote}:{camera.port}
        </div>
        <div className="text-muted-foreground">
          <span>MAC</span> <span>{texteMac(camera.mac)}</span>
        </div>
      </TableCell>
      <TableCell>
        {camera.active ? (
          <span className="flex items-center gap-1.5 text-13">
            <span className={cn("size-2 shrink-0 rounded-full", COULEURS_ETAT[camera.etat])} aria-hidden="true" />
            {texteEtat(camera.etat)}
            {raison && <span className="text-muted-foreground"> ({raison})</span>}
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-13 text-muted-foreground">
            <span className="size-2 shrink-0 rounded-full border border-unknown" aria-hidden="true" />
            Désactivée
          </span>
        )}
      </TableCell>
      <TableCell className="font-mono text-xs">{texteCodec(camera.codec)}</TableCell>
      <TableCell>
        <div className="flex items-center gap-2">
          <Switch
            aria-label="Enregistrement"
            checked={camera.enregistrement}
            disabled={!camera.active}
            onCheckedChange={onEnregistrement}
          />
          <span className={cn("text-13", camera.etat_enregistrement === "en_erreur" && "text-destructive")}>
            {texteEtatEnregistrement(camera.etat_enregistrement)}
          </span>
          <span className="text-13 text-muted-foreground">· {texteAgeSegment(camera.age_dernier_segment_s)}</span>
        </div>
        <div className="mt-0.5 font-mono text-xs text-muted-foreground">{camera.dossier_enregistrement}</div>
      </TableCell>
      <TableCell className="text-right">
        <Button variant="outline" size="sm" onClick={onReglages}>
          <Settings2 />
          Réglages
        </Button>
      </TableCell>
    </TableRow>
  );
}
