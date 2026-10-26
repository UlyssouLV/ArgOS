import { useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { useNavigate } from "react-router";
import { Calendar, CalendarX, ChevronLeft, ChevronRight, CircleAlert, MousePointerClick, Pause, Play } from "lucide-react";

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
  aRenouveler,
  dureeS,
  fenetreDansLaPlage,
  fenetreDepuis,
  finDeFenetre,
  memeFenetre,
  plageCourante,
  plageSuivante,
  plagesEnregistrees,
  type Fenetre,
  type Intervalle,
} from "./plages";
import {
  VITESSES,
  graduationsDuJour,
  instantSurLeJour,
  jourSelectionnable,
  jourVoisin,
  lireSegments,
  placeDeLInstant,
  placeSurLeJour,
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
 * en-tête (Caméra, jour), viewer, puis Timeline d'enregistrement de 00h à 24h. Un clic sur une Plage enregistrée lit
 * une fenêtre depuis la seconde visée (ADR 0018), même en pleine lecture ; un clic dans un trou, ou la fin d'une
 * Plage, passe au début de la Plage suivante du jour, et après la dernière la lecture s'arrête. Avant la fin d'une
 * fenêtre, sa suite se précharge dans une seconde vidéo, cachée, qui prend le relais à la fin, à la même vitesse : pas
 * d'interruption visible.
 */
export function RelectureCamera({ camera, cameras, jour, onJour }: PropsRelecture) {
  const naviguer = useNavigate();
  const video = useRef<HTMLVideoElement>(null);
  const champJour = useRef<HTMLInputElement>(null);
  const [lue, setLue] = useState<SegmentsFermes | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  // Figée au clic : un rafraîchissement qui prolonge la Plage ne recharge pas la vidéo.
  const [lecture, setLecture] = useState<Fenetre | null>(null);
  // Suite préchargée, figée à sa demande : un rafraîchissement qui prolonge la Plage ne la recharge pas avant le relais.
  const [suivante, setSuivante] = useState<Fenetre | null>(null);
  // Instant (ms) où la fenêtre lue s'est achevée au bout de sa Plage connue, en attente d'un Segment qui la prolonge.
  const [acheve, setAcheve] = useState<number | null>(null);
  const [etat, setEtat] = useState<EtatViewer>("lisible");
  const [vitesse, setVitesse] = useState<Vitesse>(1);
  const [enPause, setEnPause] = useState(true);
  const [position, setPosition] = useState(0);

  // Changer de Caméra ou de jour recharge la Timeline et arrête la fenêtre en cours : elle n'est plus sur ce jour.
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
    lireFenetre(null);
    setAcheve(null);
    void lire();
    const minuterie = setInterval(() => void lire(), RAFRAICHISSEMENT_MS);
    return () => {
      annule = true;
      clearInterval(minuterie);
    };
  }, [camera.id, jour]);

  const plages = useMemo(() => (lue === null ? [] : plagesEnregistrees(lue.segments)), [lue]);
  const instantLu = lecture === null ? null : Date.parse(lecture.start) + position * 1000;
  const plageLue = lecture === null ? null : plageCourante(plages, Date.parse(lecture.start));
  // Décidé avant de donner une source à la vidéo : sinon son échec masquerait le message (comme au Live).
  const h265Illisible = useMemo(
    () => camera.codec === "H265" && !hevcDecodable(document.createElement("video")),
    [camera.codec],
  );

  // À l'approche de la fin, la suite (dans la Plage, ou au début de la suivante) se demande une fois, cachée.
  useEffect(() => {
    if (suivante !== null || lue === null || lecture === null || h265Illisible) return;
    if (!aRenouveler(lecture, position, vitesse)) return;
    setSuivante(fenetreDepuis(lue.segments, finDeFenetre(lecture)));
  }, [lue, lecture, position, vitesse, suivante, h265Illisible]);

  /** Fenêtre à lire, depuis son début ; position, état et suite repartent avec elle, sans rendu intermédiaire. */
  function lireFenetre(fenetre: Fenetre | null) {
    setLecture(fenetre);
    setSuivante(null);
    setPosition(0);
    setEtat("lisible");
  }

  /** Fin de la fenêtre lue : la suite préchargée prend le relais, sinon on passe à la Plage suivante, ou on attend. */
  function enchainer(finie: Fenetre) {
    const fin = finDeFenetre(finie);
    const suite = suivante ?? (lue === null ? null : fenetreDepuis(lue.segments, fin));
    if (suite !== null) lireFenetre(suite);
    else setAcheve(fin);
  }

  // Relais par la suite préchargée : ses métadonnées sont déjà là, elle ne relance pas `onLoadedMetadata`.
  useEffect(() => {
    const lecteur = video.current;
    // Une suite préchargée en échec ne relance pas `onError` en prenant le relais.
    if (lecteur?.error) surErreur();
    if (lecteur === null || lecteur.readyState < HTMLMediaElement.HAVE_METADATA) return;
    lecteur.playbackRate = vitesse;
    void lecteur.play().catch(() => {});
  }, [lecture]);

  // Fin de la dernière Plage connue : en pause, on reprend seulement si un Segment fermé depuis la prolonge ; une
  // Plage apparue plus loin, après un trou, attend un clic.
  useEffect(() => {
    if (lue === null || acheve === null) return;
    const suite = fenetreDansLaPlage(lue.segments, acheve);
    if (suite === null) return;
    setAcheve(null);
    lireFenetre(suite);
  }, [lue, acheve]);

  useEffect(() => {
    if (video.current === null) return;
    video.current.defaultPlaybackRate = vitesse;
    video.current.playbackRate = vitesse;
  }, [vitesse]);

  function instantVise(event: MouseEvent<HTMLButtonElement>, jourLu: SegmentsFermes): number {
    // Au clavier (Entrée, Espace), pas de position : on passe au début de la Plage suivante, ou de la première.
    if (event.detail === 0) {
      const suivante = instantLu === null ? null : plageSuivante(plages, instantLu);
      return Date.parse((suivante ?? plages[0]).debut);
    }
    const boite = event.currentTarget.getBoundingClientRect();
    return instantSurLeJour(jourLu, (event.clientX - boite.left) / boite.width);
  }

  function viser(event: MouseEvent<HTMLButtonElement>) {
    if (lue === null) return;
    const visee = fenetreDepuis(lue.segments, instantVise(event, lue));
    if (visee === null) return;
    // Même fenêtre, même `src` : la vidéo ne se recharge pas, on la rembobine.
    if (memeFenetre(visee, lecture) && video.current !== null) {
      video.current.currentTime = 0;
      void video.current.play().catch(() => {});
    }
    setAcheve(null);
    lireFenetre(visee);
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
              {/* Icône calendrier de Chrome remplacée par un bouton : son contour de focus ne se règle pas en CSS. */}
              <div className="relative">
                <Input
                  ref={champJour}
                  type="date"
                  aria-label="Jour"
                  className="w-40 pr-9 font-mono [&::-webkit-calendar-picker-indicator]:hidden"
                  value={jourLu ?? ""}
                  min={lue?.premier_jour}
                  max={lue?.dernier_jour}
                  disabled={lue === null}
                  required
                  onChange={(e) => choisirJour(e.target.value)}
                />
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Ouvrir le calendrier"
                  className="absolute inset-y-0 right-0 h-full"
                  disabled={lue === null}
                  onClick={() => champJour.current?.showPicker()}
                >
                  <Calendar />
                </Button>
              </div>
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
          {/* Une seule liste à clé = URL : au relais, la vidéo préchargée reste le même élément, sans recharger son `src`. */}
          {[lecture, suivante].map((fenetre) => {
            if (fenetre === null) return null;
            const url = urlRelecture(cheminFlux(camera.id), fenetre);
            if (fenetre !== lecture) {
              return (
                <video
                  key={url}
                  className="invisible absolute inset-0 size-full object-contain"
                  src={url}
                  preload="auto"
                  muted
                  playsInline
                  aria-hidden="true"
                  onLoadedMetadata={(e) => {
                    e.currentTarget.playbackRate = vitesse;
                  }}
                />
              );
            }
            return (
              <video
                key={url}
                ref={video}
                className="size-full object-contain"
                src={h265Illisible ? undefined : url}
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
                onEnded={() => enchainer(fenetre)}
                onError={surErreur}
              />
            );
          })}
          {lecture !== null && h265Illisible && <MessageVideo>Ce navigateur ne lit pas le H.265</MessageVideo>}
          {lecture !== null && !h265Illisible && etat === "indisponible" && (
            <MessageVideo>Enregistrement indisponible</MessageVideo>
          )}
          {lecture === null && lue?.segments.length === 0 && (
            <MessageVideo>
              <CalendarX className="size-6" aria-hidden="true" />
              Aucun enregistrement ce jour
            </MessageVideo>
          )}
          {lecture === null && lue !== null && lue.segments.length > 0 && (
            <MessageVideo>
              <MousePointerClick className="size-6" aria-hidden="true" />
              Cliquez sur la Timeline pour relire une Plage.
            </MessageVideo>
          )}
        </div>
        {instantLu !== null && lue !== null && !h265Illisible && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <Button variant="outline" size="sm" onClick={basculer}>
              {enPause ? <Play /> : <Pause />}
              {enPause ? "Lecture" : "Pause"}
            </Button>
            <span className="font-mono text-sm" aria-label="Instant lu">
              {heureDuSite(instantLu, lue.fuseau)}
            </span>
            {plageLue !== null && (
              <progress
                aria-label="Progression dans la Plage"
                className="h-1.5 min-w-24 flex-1 overflow-hidden rounded-full [&::-moz-progress-bar]:bg-foreground [&::-webkit-progress-bar]:bg-muted [&::-webkit-progress-value]:bg-foreground"
                max={dureeS(plageLue)}
                value={(instantLu - Date.parse(plageLue.debut)) / 1000}
              />
            )}
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
                  className="h-7 rounded-sm px-2.5 font-mono text-xs text-muted-foreground anneau-focus hover:text-foreground aria-pressed:bg-secondary aria-pressed:text-foreground"
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
            <TimelineDuJour
              lue={lue}
              plages={plages}
              plageLue={plageLue}
              tete={instantLu === null ? null : placeDeLInstant(lue, instantLu)}
              onClic={viser}
            />
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

/**
 * Timeline d'enregistrement d'un jour : trous sur le fond, Plages enregistrées en couleur, tête de lecture à l'instant
 * lu (docs/glossaire.md).
 */
function TimelineDuJour({
  lue,
  plages,
  plageLue,
  tete,
  onClic,
}: Readonly<{
  lue: SegmentsFermes;
  plages: Intervalle[];
  plageLue: Intervalle | null;
  /** Place de l'instant lu, en pourcentage du jour ; `null` hors lecture. */
  tete: number | null;
  onClic: (event: MouseEvent<HTMLButtonElement>) => void;
}>) {
  const graduations = graduationsDuJour(lue);
  return (
    <>
      <button
        type="button"
        aria-label="Timeline d’enregistrement"
        onClick={onClic}
        disabled={lue.segments.length === 0}
        className="relative block h-10 w-full cursor-pointer overflow-hidden rounded-md bg-muted anneau-focus disabled:cursor-default"
      >
        {graduations.map(({ place }) => (
          <span key={place} className="absolute inset-y-0 w-px bg-border" style={{ left: `${place}%` }} aria-hidden="true" />
        ))}
        {plages.map((p) => {
          const { gauche, largeur } = placeSurLeJour(lue, p);
          const plage = `${heureDuSite(Date.parse(p.debut), lue.fuseau)} → ${heureDuSite(Date.parse(p.fin), lue.fuseau)}`;
          const enLecture = p.debut === plageLue?.debut;
          return (
            <span
              key={p.debut}
              role="img"
              aria-label={`${enLecture ? "Plage lue" : "Plage enregistrée"} ${plage}`}
              className={cn("absolute inset-y-1 min-w-0.5 bg-success/80", enLecture && "bg-foreground")}
              style={{ left: `${gauche}%`, width: `${largeur}%` }}
              title={plage}
            />
          );
        })}
        {tete !== null && (
          <span
            role="img"
            aria-label="Tête de lecture"
            className="absolute inset-y-0 w-0.5 -translate-x-1/2 bg-brand"
            style={{ left: `${tete}%` }}
          />
        )}
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
