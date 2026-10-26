import { useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { CalendarX, ChevronLeft, ChevronRight, CircleAlert, MousePointerClick, Pause, Play } from "lucide-react";

import { EnTeteDePage } from "@/components/EnTeteDePage";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import { sessionValide } from "./api";
import { messageEchec, texteEtat, type Camera, type Etat } from "./cameras";
import { hevcDecodable } from "./hls";
import {
  VITESSES,
  dureeS,
  graduationsDuJour,
  instantSurLeJour,
  jourSelectionnable,
  jourVoisin,
  lireSegments,
  placeSurLeJour,
  segmentSuivant,
  segmentVise,
  urlRelecture,
  type SegmentsFermes,
  type Vitesse,
} from "./relecture";

type PropsRelecture = Readonly<{
  camera: Camera;
  cameras: Camera[];
  /** Jour du Site relu (`AAAA-MM-JJ`) ; `null` : le jour courant. Gardé par la page d'une Caméra à l'autre. */
  jour: string | null;
  onJour: (jour: string) => void;
}>;

type EtatViewer = "lisible" | "indisponible";

/** Les Segments fermés depuis rejoignent la timeline, et la Conservation avance. */
const RAFRAICHISSEMENT_MS = 10_000;

const COULEURS_ETAT: Record<Etat, string> = {
  online: "bg-success",
  offline: "bg-destructive",
  unknown: "bg-unknown",
};

/**
 * Chemin du pont d'une Caméra, aussi celui de ses enregistrements (`camera-<id>`, ADR 0011). Recalculé ici :
 * l'API ne donne `chemin_flux` qu'à une Caméra activée, et une Caméra désactivée garde ses Segments.
 */
function cheminFlux(idCamera: number): string {
  return `camera-${idCamera}`;
}

/** Heure du Site d'un instant (ms), à la seconde. */
function heureDuSite(instant: number, fuseau: string): string {
  return new Date(instant).toLocaleTimeString("fr-FR", { timeZone: fuseau });
}

function dateDuSite(iso: string, fuseau: string): string {
  return new Date(iso).toLocaleString("fr-FR", { timeZone: fuseau, dateStyle: "medium", timeStyle: "short" });
}

/**
 * Relecture d'une Caméra, un jour du Site à la fois (docs/adr/0013-relecture-des-enregistrements.md, ADR 0017) :
 * en-tête (Caméra, jour), viewer du Segment visé, puis Timeline d'enregistrement de 00h à 24h. Un clic part du
 * début du Segment qui couvre l'instant, ou du plus proche ; à la fin d'un Segment, le viewer enchaîne sur le
 * suivant, à la même vitesse.
 */
export function RelectureCamera({ camera, cameras, jour, onJour }: PropsRelecture) {
  const naviguer = useNavigate();
  const video = useRef<HTMLVideoElement>(null);
  const [lue, setLue] = useState<SegmentsFermes | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  // Segments repérés par leur début : un rafraîchissement décale leurs index.
  const [courant, setCourant] = useState<string | null>(null);
  const [acheve, setAcheve] = useState<string | null>(null);
  const [etat, setEtat] = useState<EtatViewer>("lisible");
  const [vitesse, setVitesse] = useState<Vitesse>(1);
  const [enPause, setEnPause] = useState(true);
  const [position, setPosition] = useState(0);

  // Changer de jour recharge la Timeline et laisse le Segment en cours : il n'est plus sur ce jour.
  useEffect(() => {
    let annule = false;
    const lire = () =>
      lireSegments(camera.id, jour)
        .then((segments) => {
          if (annule) return;
          setLue(segments);
          setErreur(null);
        })
        .catch((e: unknown) => !annule && setErreur(messageEchec(e)));
    setLue(null);
    setCourant(null);
    setAcheve(null);
    void lire();
    const minuterie = setInterval(() => void lire(), RAFRAICHISSEMENT_MS);
    return () => {
      annule = true;
      clearInterval(minuterie);
    };
  }, [camera.id, jour]);

  const segment = lue?.segments.find((s) => s.debut === courant) ?? null;
  // Décidé avant de donner une source à la vidéo : sinon son échec masquerait le message (comme au Live).
  const h265Illisible = useMemo(
    () => camera.codec === "H265" && !hevcDecodable(document.createElement("video")),
    [camera.codec],
  );

  useEffect(() => {
    setPosition(0);
    setEtat("lisible");
  }, [courant]);

  // Fin du dernier Segment connu : on enchaîne dès qu'un rafraîchissement apporte le Segment fermé ensuite.
  useEffect(() => {
    if (lue === null || acheve === null) return;
    const suivant = segmentSuivant(lue.segments, acheve);
    if (suivant === null) return;
    setAcheve(null);
    setCourant(suivant.debut);
  }, [lue, acheve]);

  useEffect(() => {
    if (video.current === null) return;
    video.current.defaultPlaybackRate = vitesse;
    video.current.playbackRate = vitesse;
  }, [vitesse]);

  function debutVise(event: MouseEvent<HTMLButtonElement>, jourLu: SegmentsFermes): string | null {
    const { segments } = jourLu;
    // Au clavier (Entrée, Espace), pas de position : on passe au Segment suivant, ou au premier.
    if (event.detail === 0) {
      const suivant = courant === null ? null : segmentSuivant(segments, courant);
      return (suivant ?? segments[0]).debut;
    }
    const boite = event.currentTarget.getBoundingClientRect();
    const fraction = (event.clientX - boite.left) / boite.width;
    const vise = segmentVise(segments, instantSurLeJour(jourLu, fraction));
    return vise === null ? null : segments[vise].debut;
  }

  function viser(event: MouseEvent<HTMLButtonElement>) {
    if (lue === null) return;
    const debut = debutVise(event, lue);
    if (debut === null) return;
    if (debut === courant && video.current !== null) video.current.currentTime = 0;
    setAcheve(null);
    setCourant(debut);
  }

  function surErreur() {
    // sessionValide ne rejette jamais : un 401 renvoie déjà à la connexion.
    void sessionValide().then((valide) => valide && setEtat("indisponible"));
  }

  function basculer() {
    const lecteur = video.current!;
    if (lecteur.paused) void lecteur.play().catch(() => {});
    else lecteur.pause();
  }

  function choisirJour(choisi: string) {
    if (lue !== null && jourSelectionnable(lue, choisi)) onJour(choisi);
  }

  const jourLu = lue?.jour ?? jour;

  return (
    <>
      <EnTeteDePage
        titre="Relecture"
        actions={
          <div className="flex flex-wrap items-center justify-end gap-x-4 gap-y-2">
            <div className="flex items-center gap-3">
              <NativeSelect
                aria-label="Caméra"
                className="w-48"
                value={camera.id}
                onChange={(e) => void naviguer(`/relecture/${e.target.value}`)}
              >
                {cameras.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.nom}
                  </option>
                ))}
              </NativeSelect>
              <span className="flex items-center gap-1.5 text-13">
                <span className={cn("size-2 rounded-full", COULEURS_ETAT[camera.etat])} aria-hidden="true" />
                {texteEtat(camera.etat)}
              </span>
            </div>
            <div role="group" aria-label="Jour relu" className="flex items-center gap-1">
              <Button
                variant="outline"
                size="icon"
                aria-label="Jour précédent"
                disabled={lue === null || !jourSelectionnable(lue, jourVoisin(lue.jour, -1))}
                onClick={() => lue && choisirJour(jourVoisin(lue.jour, -1))}
              >
                <ChevronLeft />
              </Button>
              <Input
                type="date"
                aria-label="Jour"
                className="w-40 font-mono [color-scheme:dark]"
                value={jourLu ?? ""}
                min={lue?.premier_jour}
                max={lue?.dernier_jour}
                disabled={lue === null}
                required
                onChange={(e) => choisirJour(e.target.value)}
              />
              <Button
                variant="outline"
                size="icon"
                aria-label="Jour suivant"
                disabled={lue === null || !jourSelectionnable(lue, jourVoisin(lue.jour, 1))}
                onClick={() => lue && choisirJour(jourVoisin(lue.jour, 1))}
              >
                <ChevronRight />
              </Button>
            </div>
          </div>
        }
      />
      <section aria-label={`Relecture — ${camera.nom}`} className="flex flex-col gap-4 p-6">
        {erreur && (
          <Alert variant="destructive">
            <CircleAlert />
            <AlertDescription>{erreur}</AlertDescription>
          </Alert>
        )}
        <div className="relative aspect-video max-h-[60vh] w-full overflow-hidden rounded-lg border bg-video">
          {segment !== null && (
            <video
              ref={video}
              className="size-full object-contain"
              src={h265Illisible ? undefined : urlRelecture(cheminFlux(camera.id), segment)}
              autoPlay
              muted
              playsInline
              onLoadedMetadata={(e) => {
                e.currentTarget.playbackRate = vitesse;
                // `autoPlay` seul ne part pas toujours sur un MP4 d'une minute (Chromium) : on lance la lecture.
                void e.currentTarget.play().catch(() => {});
              }}
              onPlay={() => setEnPause(false)}
              onPause={() => setEnPause(true)}
              onTimeUpdate={(e) => setPosition(e.currentTarget.currentTime)}
              onEnded={() => setAcheve(courant)}
              onError={surErreur}
            />
          )}
          {segment !== null && h265Illisible && <MessageVideo>Ce navigateur ne lit pas le H.265</MessageVideo>}
          {segment !== null && !h265Illisible && etat === "indisponible" && (
            <MessageVideo>Enregistrement indisponible</MessageVideo>
          )}
          {segment === null && lue?.segments.length === 0 && (
            <MessageVideo>
              <CalendarX className="size-6" aria-hidden="true" />
              Aucun enregistrement ce jour
            </MessageVideo>
          )}
          {segment === null && lue !== null && lue.segments.length > 0 && (
            <MessageVideo>
              <MousePointerClick className="size-6" aria-hidden="true" />
              Cliquez sur la timeline pour relire un Segment.
            </MessageVideo>
          )}
        </div>
        {segment !== null && lue !== null && !h265Illisible && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <Button variant="outline" size="sm" onClick={basculer}>
              {enPause ? <Play /> : <Pause />}
              {enPause ? "Lecture" : "Pause"}
            </Button>
            <span className="font-mono text-sm" aria-label="Instant lu">
              {heureDuSite(Date.parse(segment.debut) + position * 1000, lue.fuseau)}
            </span>
            <progress
              aria-label="Progression dans le Segment"
              className="h-1.5 min-w-24 flex-1 overflow-hidden rounded-full [&::-moz-progress-bar]:bg-foreground [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:bg-foreground"
              max={dureeS(segment)}
              value={position}
            />
            <div
              role="group"
              aria-label="Vitesse de lecture"
              className="inline-flex rounded-md border bg-card p-0.5"
            >
              {VITESSES.map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={v === vitesse}
                  onClick={() => setVitesse(v)}
                  className="h-7 rounded-sm px-2.5 font-mono text-xs text-muted-foreground outline-none hover:text-foreground focus-visible:ring-[3px] focus-visible:ring-ring aria-pressed:bg-secondary aria-pressed:text-foreground"
                >
                  ×{v}
                </button>
              ))}
            </div>
          </div>
        )}
        <div className="rounded-lg border bg-card p-4">
          {lue === null ? (
            <Skeleton className="h-14 w-full" aria-busy="true" />
          ) : (
            <TimelineDuJour lue={lue} courant={courant} onClic={viser} />
          )}
        </div>
      </section>
    </>
  );
}

function MessageVideo({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <p className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-video/80 p-4 text-center text-muted-foreground">
      {children}
    </p>
  );
}

/** Timeline d'enregistrement d'un jour : trous sur le fond, plages enregistrées en couleur (docs/glossaire.md). */
function TimelineDuJour({
  lue,
  courant,
  onClic,
}: Readonly<{ lue: SegmentsFermes; courant: string | null; onClic: (event: MouseEvent<HTMLButtonElement>) => void }>) {
  const graduations = graduationsDuJour(lue);
  return (
    <>
      <button
        type="button"
        aria-label="Timeline d’enregistrement"
        onClick={onClic}
        disabled={lue.segments.length === 0}
        className="relative block h-10 w-full cursor-pointer overflow-hidden rounded-md bg-muted outline-none focus-visible:ring-[3px] focus-visible:ring-ring disabled:cursor-default"
      >
        {graduations.map(({ place }) => (
          <span key={place} className="absolute inset-y-0 w-px bg-border" style={{ left: `${place}%` }} aria-hidden="true" />
        ))}
        {lue.segments.map((s) => {
          const { gauche, largeur } = placeSurLeJour(lue, s);
          return (
            <span
              key={s.debut}
              className={cn(
                "plage-enregistree absolute inset-y-1 min-w-0.5 bg-success/80",
                s.debut === courant && "plage-courante bg-foreground",
              )}
              style={{ left: `${gauche}%`, width: `${largeur}%` }}
              title={`${heureDuSite(Date.parse(s.debut), lue.fuseau)} → ${heureDuSite(Date.parse(s.fin), lue.fuseau)}`}
            />
          );
        })}
      </button>
      <div className="relative mt-1 h-4 font-mono text-xs text-muted-foreground" aria-hidden="true">
        {graduations.map(({ place, libelle }) => (
          <span
            key={place}
            className={cn("absolute", place > 0 && "-translate-x-1/2", place === 100 && "-translate-x-full")}
            style={{ left: `${place}%` }}
          >
            {libelle}
          </span>
        ))}
      </div>
      <p className="mt-3 text-13 text-muted-foreground">
        Conservation : du {dateDuSite(lue.debut, lue.fuseau)} au {dateDuSite(lue.fin, lue.fuseau)} (heure du Site,{" "}
        {lue.fuseau}).
      </p>
    </>
  );
}
