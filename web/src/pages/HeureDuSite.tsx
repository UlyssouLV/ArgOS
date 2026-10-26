import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Clock, RefreshCw } from "lucide-react";

import { EnTeteDePage } from "@/components/EnTeteDePage";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { notifier } from "@/notifier";
import { messageEchec } from "../cameras";
import {
  libelleEtatHorloge,
  lireFuseaux,
  lireHeureDuSite,
  lireHorlogesDesCameras,
  modifierHeureDuSite,
  MOTIF_SERVEUR_NTP,
  texteBaseDesFuseaux,
  texteBilanVerification,
  texteEcart,
  texteHeure,
  texteSourceUtilisee,
  verifierLesCameras,
  type EtatHorloge,
  type HeureDuSite as Heure,
  type HorlogeVerifiee,
  type Source,
} from "../heureSite";

// Relecture de ce que sert le Serveur de temps du Site (source utilisée, repli) et du tableau des Caméras.
const RAFRAICHISSEMENT_MS = 10_000;

// Pastille de la Mise à l'heure, toujours suivie de son libellé ; jamais vérifiée : cerclée.
const COULEURS_ETAT: Record<EtatHorloge, string> = {
  a_l_heure: "bg-success",
  ecart: "bg-destructive",
  sans_onvif: "bg-unknown",
  echec: "bg-destructive",
};

const COLONNES = ["Caméra", "Mise à l’heure", "Dérive", "Écart", "Dernière vérification"];

/** Page Heure du Site de l'Administration (docs/adr/0014-serveur-de-temps-du-site.md). */
export function HeureDuSite() {
  const [heure, setHeure] = useState<Heure | null>(null);
  // Écart entre l'heure servie et celle du navigateur à la dernière lecture : l'heure affichée avance seule.
  const [ecartMs, setEcartMs] = useState<number | null>(null);
  const [maintenant, setMaintenant] = useState(() => Date.now());
  const [fuseaux, setFuseaux] = useState<string[]>([]);
  const [source, setSource] = useState<Source>("ntp");
  const [serveur, setServeur] = useState("");
  const [fuseau, setFuseau] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);
  const [horloges, setHorloges] = useState<HorlogeVerifiee[] | null>(null);
  const [verificationEnCours, setVerificationEnCours] = useState(false);

  const montrer = useCallback((lue: Heure, saisie: boolean) => {
    setHeure(lue);
    setEcartMs(lue.heure === null ? null : Date.parse(lue.heure) - Date.now());
    if (saisie) {
      setSource(lue.source);
      setServeur(lue.serveur_ntp);
      setFuseau(lue.fuseau);
    }
  }, []);

  const rafraichir = useCallback(
    async (saisie: boolean) => {
      try {
        const [lue, cameras] = await Promise.all([lireHeureDuSite(), lireHorlogesDesCameras()]);
        montrer(lue, saisie);
        setHorloges(cameras);
        setErreur(null);
      } catch (e) {
        setErreur(messageEchec(e));
      }
    },
    [montrer],
  );

  useEffect(() => {
    void rafraichir(true);
    void lireFuseaux().then(setFuseaux, (e: unknown) => setErreur(messageEchec(e)));
    const relecture = setInterval(() => void rafraichir(false), RAFRAICHISSEMENT_MS);
    const seconde = setInterval(() => setMaintenant(Date.now()), 1000);
    return () => {
      clearInterval(relecture);
      clearInterval(seconde);
    };
  }, [rafraichir]);

  async function enregistrer(event: FormEvent) {
    event.preventDefault();
    if (heure === null) return;
    setEnCours(true);
    try {
      montrer(
        await modifierHeureDuSite({ source, fuseau, ...(source === "ntp" ? { serveur_ntp: serveur.trim() } : {}) }),
        true,
      );
      notifier("Heure du Site enregistrée : les Caméras actives sont mises à l’heure et recalées.");
    } catch (e) {
      const message = messageEchec(e);
      if (message) notifier(message, "echec");
    } finally {
      setEnCours(false);
    }
  }

  async function verifierMaintenant() {
    setVerificationEnCours(true);
    try {
      const verifiees = await verifierLesCameras();
      setHorloges(verifiees);
      notifier(texteBilanVerification(verifiees));
    } catch (e) {
      const message = messageEchec(e);
      if (message) notifier(message, "echec");
    } finally {
      setVerificationEnCours(false);
    }
  }

  const inchangee =
    heure !== null &&
    source === heure.source &&
    fuseau === heure.fuseau &&
    (source === "horloge_serveur" || serveur.trim() === heure.serveur_ntp);
  // Le fuseau du Site reste proposé même s'il n'est pas parmi les fuseaux courants (celui de l'hôte).
  const fuseauxProposes = heure && !fuseaux.includes(heure.fuseau) ? [heure.fuseau, ...fuseaux] : fuseaux;

  return (
    <>
      <EnTeteDePage
        titre="Heure du Site"
        surtitre="Administration"
        actions={
          <Button disabled={verificationEnCours} onClick={() => void verifierMaintenant()}>
            <RefreshCw className={cn(verificationEnCours && "animate-spin")} />
            {verificationEnCours ? "Vérification…" : "Vérifier maintenant"}
          </Button>
        }
      />
      <div className="flex flex-col gap-6 p-6">
        {erreur && (
          <Alert variant="destructive">
            <AlertDescription>{erreur}</AlertDescription>
          </Alert>
        )}
        <Card>
          <CardHeader>
            <CardTitle>Réglage</CardTitle>
            <CardDescription>
              Enregistrer met à l’heure et recale toutes les Caméras actives : serveur NTP = le Site, fuseau = celui
              du Site.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-8 lg:grid-cols-2">
            {heure ? (
              <dl className="grid content-start gap-4" aria-label="Heure du Site">
                <Valeur terme="Heure actuelle du Site">
                  <span className="font-mono text-2xl tabular-nums">
                    {texteHeure(ecartMs === null ? null : new Date(maintenant + ecartMs), heure.fuseau)}
                  </span>
                </Valeur>
                <Valeur terme="Source utilisée">{texteSourceUtilisee(heure)}</Valeur>
                <Valeur terme="Fuseau">
                  {heure.fuseau}
                  {heure.fuseau_de_l_hote && " (celui du serveur)"}
                </Valeur>
                <Valeur terme="Adresse du Serveur de temps">
                  {heure.adresse_serveur_de_temps ? (
                    <span className="font-mono">{heure.adresse_serveur_de_temps}</span>
                  ) : (
                    <span className="text-destructive">
                      inconnue : renseigner l’IP du Site (MTX_WEBRTCADDITIONALHOSTS) ; aucune Caméra n’est calée
                    </span>
                  )}
                </Valeur>
                <Valeur terme="Base des fuseaux">{texteBaseDesFuseaux(heure.base_des_fuseaux)}</Valeur>
              </dl>
            ) : (
              !erreur && <SquelettesHeure />
            )}
            <form
              className="grid content-start gap-5"
              aria-label="Régler l’Heure du Site"
              onSubmit={(e) => void enregistrer(e)}
            >
              <fieldset className="grid gap-3" disabled={heure === null || enCours}>
                <legend className="mb-3 text-sm font-medium">Source de l’heure</legend>
                <Label className="font-normal">
                  <input
                    type="radio"
                    name="source"
                    className="size-4 accent-brand"
                    checked={source === "ntp"}
                    onChange={() => setSource("ntp")}
                  />
                  Serveur NTP externe
                </Label>
                <div className="grid gap-1.5 pl-6">
                  <Label htmlFor="serveur-ntp" className="text-13 text-muted-foreground">
                    Adresse du serveur NTP
                  </Label>
                  <Input
                    id="serveur-ntp"
                    type="text"
                    className="font-mono"
                    value={serveur}
                    required={source === "ntp"}
                    pattern={MOTIF_SERVEUR_NTP}
                    disabled={source !== "ntp"}
                    onChange={(e) => setServeur(e.target.value)}
                  />
                </div>
                <Label className="font-normal">
                  <input
                    type="radio"
                    name="source"
                    className="size-4 accent-brand"
                    checked={source === "horloge_serveur"}
                    onChange={() => setSource("horloge_serveur")}
                  />
                  Horloge du serveur
                </Label>
                <p className="text-13 text-muted-foreground">
                  Un serveur NTP injoignable laisse le Site servir l’horloge du serveur, jusqu’à ce qu’il réponde.
                </p>
              </fieldset>
              <div className="grid gap-1.5">
                <Label htmlFor="fuseau-du-site">Fuseau du Site</Label>
                <NativeSelect
                  id="fuseau-du-site"
                  value={fuseau}
                  disabled={heure === null || enCours}
                  onChange={(e) => setFuseau(e.target.value)}
                >
                  {fuseauxProposes.map((nom) => (
                    <option key={nom} value={nom}>
                      {nom}
                    </option>
                  ))}
                </NativeSelect>
              </div>
              <div>
                <Button type="submit" disabled={heure === null || inchangee || enCours}>
                  Enregistrer
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
        <section className="flex flex-col gap-3" aria-labelledby="titre-horloges-cameras">
          <div>
            <h2 id="titre-horloges-cameras" className="text-base font-semibold">
              Caméras
            </h2>
            <p className="text-13 text-muted-foreground">
              Vérifiées toutes les heures : chaque Caméra est mise à l’heure du Serveur de temps du Site, puis recalée
              dessus. La dérive est mesurée avant, l’écart après ; au-delà de 2 s d’écart, elle n’est pas à l’heure.
            </p>
          </div>
          {horloges === null && !erreur && <SquelettesCameras />}
          {horloges?.length === 0 && <AucuneCameraActive />}
          {horloges && horloges.length > 0 && (
            <div className="rounded-lg border bg-card">
              <Table aria-label="Caméras">
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    {COLONNES.map((colonne) => (
                      <TableHead key={colonne}>{colonne}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {horloges.map((camera) => (
                    <LigneHorloge key={camera.id} camera={camera} />
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </section>
      </div>
    </>
  );
}

function Valeur({ terme, children }: Readonly<{ terme: string; children: ReactNode }>) {
  return (
    <div className="grid gap-1">
      <dt className="text-13 text-muted-foreground">{terme}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function SquelettesHeure() {
  return (
    <div className="grid content-start gap-4" aria-busy="true" aria-label="Chargement de l’Heure du Site">
      <Skeleton className="h-8 w-3/4" />
      {[0, 1, 2, 3].map((rang) => (
        <Skeleton key={rang} className="h-5 w-1/2" />
      ))}
    </div>
  );
}

function SquelettesCameras() {
  return (
    <div className="space-y-2 rounded-lg border bg-card p-4" aria-busy="true" aria-label="Chargement des Caméras">
      {[0, 1, 2].map((rang) => (
        <Skeleton key={rang} className="h-10 w-full" />
      ))}
    </div>
  );
}

/** État vide : rien à mettre à l'heure tant qu'aucune Caméra n'est active. */
function AucuneCameraActive() {
  return (
    <section
      aria-label="Aucune Caméra active"
      className="flex flex-col items-center gap-3 rounded-lg border border-dashed bg-card px-6 py-12 text-center"
    >
      <Clock className="size-8 text-muted-foreground" aria-hidden="true" />
      <p className="text-base font-semibold">Aucune Caméra active</p>
      <p className="text-muted-foreground">Les Caméras actives sont mises à l’heure du Site dès leur ajout.</p>
    </section>
  );
}

function LigneHorloge({ camera }: Readonly<{ camera: HorlogeVerifiee }>) {
  return (
    <TableRow>
      <TableCell className="font-medium">{camera.nom}</TableCell>
      <TableCell>
        <span className="flex items-center gap-1.5 text-13">
          <span
            className={cn(
              "size-2 shrink-0 rounded-full",
              camera.etat ? COULEURS_ETAT[camera.etat] : "border border-unknown",
            )}
            aria-hidden="true"
          />
          {libelleEtatHorloge(camera.etat)}
        </span>
      </TableCell>
      <TableCell className="font-mono text-xs">{texteEcart(camera.derive_s)}</TableCell>
      <TableCell className="font-mono text-xs">{texteEcart(camera.ecart_s)}</TableCell>
      <TableCell className="font-mono text-xs">
        {camera.verifiee_le === null
          ? "—"
          : new Date(camera.verifiee_le).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "medium" })}
      </TableCell>
    </TableRow>
  );
}
