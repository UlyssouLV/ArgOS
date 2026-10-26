import { Fragment, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Loader2, RefreshCw } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { notifier } from "@/notifier";
import { messageEchec, texteMac, type Camera } from "../cameras";
import {
  essayer,
  filtreMacInvalide,
  filtrerParMac,
  lancerDetection,
  lireEtatDetection,
  retirerEssai,
  type Adresse,
  type Candidat,
  type Essai,
  type EtatDetection,
  type ResultatDetection,
} from "../detection";
import { AjoutCandidat } from "./AjoutCandidat";

function couverture(sous_reseaux: string[], ports: number[]): string {
  return `${sous_reseaux.join(", ")} — ports ${ports.join(", ")}`;
}

function cle(adresse: Adresse): string {
  return `${adresse.ip}:${adresse.port}`;
}

/** Port RTSP standard, prérempli pour l'ajout par adresse IP. */
const PORT_RTSP = 554;

const SANS_CORRESPONDANCE = "Aucun Candidat ne correspond à ce filtre.";

const MAC_INVALIDE =
  "MAC invalide : chiffres 0-9 et lettres a-f seulement (séparateurs : - . acceptés), douze au plus.";

type Onglet = "candidats" | "deja";

/**
 * Panneau d'ajout ouvert : celui d'un Candidat détecté, ou d'une IP saisie avec son premier essai
 * (`numero` : chaque saisie ouvre un panneau neuf, même sur la même IP).
 */
type EnAjout = { cle: string } | { adresse: Adresse; essai: Essai; numero: number };

type Props = Readonly<{
  ouverte: boolean;
  onFermer: () => void;
  /** La liste des Caméras est à relire. */
  onCameraAjoutee: () => void;
}>;

/**
 * Boîte de dialogue « Détecter des Caméras » : la première ouverture lance une Détection, dont les Candidats se
 * lisent en deux onglets (nouveaux, « Déjà configurées ») ; « Ajouter » ouvre le panneau d'ajout sous la ligne.
 * « Ajouter par adresse IP » couvre un appareil non détecté. Un seul panneau d'ajout ouvert à la fois.
 * La Détection survit à la fermeture : rouverte, la boîte la remontre sans la relancer.
 * Une Caméra ajoutée referme la boîte et s'annonce en toast ; fermer la boîte retire l'essai en cours.
 */
export function DetecterCameras({ ouverte, onFermer, onCameraAjoutee }: Props) {
  const [etat, setEtat] = useState<EtatDetection | null>(null);
  const [resultat, setResultat] = useState<ResultatDetection | null>(null);
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enAjout, setEnAjout] = useState<EnAjout | null>(null);
  const [onglet, setOnglet] = useState<Onglet>("candidats");
  const lancee = useRef(false);

  useEffect(() => {
    lireEtatDetection()
      .then(setEtat)
      .catch((e) => setErreur(messageEchec(e)));
  }, []);

  async function detecter() {
    lancee.current = true;
    setEnCours(true);
    setErreur(null);
    setResultat(null);
    setOnglet("candidats");
    try {
      setResultat(await lancerDetection());
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnCours(false);
    }
  }

  useEffect(() => {
    if (ouverte && etat?.configuree && !lancee.current) void detecter();
  }, [ouverte, etat]);

  function fermer() {
    if (enAjout) retirerEssai().catch(() => {});
    setEnAjout(null);
    setOnglet("candidats");
    onFermer();
  }

  /** Le Candidat passe dans « Déjà configurées » sans relancer de Détection ; la boîte se referme sur la liste. */
  function ajoutee(candidat: Adresse, camera: Camera) {
    setEnAjout(null);
    setOnglet("candidats");
    setResultat(
      (courant) =>
        courant && {
          ...courant,
          candidats: courant.candidats.map((c) =>
            cle(c) === cle(candidat) ? { ...c, camera: { id: camera.id, nom: camera.nom } } : c,
          ),
        },
    );
    notifier(`Caméra ${camera.nom} ajoutée.`);
    onFermer();
    onCameraAjoutee();
  }

  return (
    <Dialog open={ouverte} onOpenChange={(ouvrir) => !ouvrir && fermer()}>
      <DialogContent className="max-h-[90vh] gap-5 overflow-y-auto sm:max-w-3xl">
        <DialogHeader className="pr-8">
          <DialogTitle className="text-xl">Détecter des Caméras</DialogTitle>
          <DialogDescription className={etat && !etat.configuree ? "text-destructive" : undefined}>
            {etat?.configuree && <>Sous-réseaux couverts : {couverture(etat.sous_reseaux, etat.ports)}</>}
            {etat && !etat.configuree && etat.raison}
          </DialogDescription>
        </DialogHeader>
        {enCours && (
          <p role="status" className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            Détection en cours…
          </p>
        )}
        {erreur && (
          <Alert variant="destructive">
            <AlertDescription>{erreur}</AlertDescription>
          </Alert>
        )}
        {resultat && (
          <Candidats
            resultat={resultat}
            onglet={onglet}
            onOnglet={setOnglet}
            enAjout={enAjout && "cle" in enAjout ? enAjout.cle : null}
            onOuvrir={(candidat) => setEnAjout({ cle: cle(candidat) })}
            onFermer={() => setEnAjout(null)}
            onAjoutee={ajoutee}
          />
        )}
        <div className="flex justify-end">
          {/* Pendant la Détection, aria-disabled plutôt que disabled : le bouton garde le focus clavier. */}
          <Button
            variant="outline"
            size="sm"
            disabled={!etat?.configuree}
            aria-disabled={enCours || undefined}
            className="aria-disabled:opacity-50"
            onClick={() => !enCours && void detecter()}
          >
            <RefreshCw />
            {resultat ? "Relancer la Détection" : "Lancer la Détection"}
          </Button>
        </div>
        <AjoutParIp
          onEssai={(adresse, essai) =>
            setEnAjout((avant) => ({ adresse, essai, numero: (avant && "numero" in avant ? avant.numero : 0) + 1 }))
          }
        />
        {enAjout && "adresse" in enAjout && (
          <AjoutCandidat
            key={enAjout.numero}
            candidat={enAjout.adresse}
            premierEssai={enAjout.essai}
            onAjoutee={(camera) => ajoutee(enAjout.adresse, camera)}
            onFermer={() => setEnAjout(null)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

type PropsAjoutParIp = Readonly<{ onEssai: (adresse: Adresse, essai: Essai) => void }>;

/**
 * « Ajouter par adresse IP » : appareil que la Détection n'a pas trouvé, même si elle n'est pas configurée.
 * Le premier essai part d'ici ; une adresse refusée (Caméra déjà configurée, hors du réseau local) s'affiche
 * dans ce formulaire sans ouvrir le panneau d'ajout.
 */
function AjoutParIp({ onEssai }: PropsAjoutParIp) {
  const id = useId();
  const [ip, setIp] = useState("");
  const [port, setPort] = useState(String(PORT_RTSP));
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  async function soumettre(evenement: FormEvent) {
    evenement.preventDefault();
    const adresse = { ip: ip.trim(), port: Number(port) };
    setEnCours(true);
    setErreur(null);
    try {
      onEssai(adresse, await essayer(adresse.ip, adresse.port));
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnCours(false);
    }
  }

  return (
    <form aria-labelledby={`${id}-titre`} className="grid gap-3 border-t pt-4" onSubmit={soumettre}>
      <h3 id={`${id}-titre`} className="font-semibold">
        Ajouter par adresse IP
      </h3>
      <div className="flex flex-wrap items-end gap-3">
        <div className="grid min-w-48 flex-1 gap-1.5">
          <Label htmlFor={`${id}-ip`}>Adresse IP</Label>
          <Input
            id={`${id}-ip`}
            name="ip"
            required
            autoComplete="off"
            pattern="\d{1,3}(\.\d{1,3}){3}"
            title="Adresse IPv4, par exemple 192.168.1.64"
            placeholder="192.168.1.64"
            className="font-mono"
            value={ip}
            onChange={(e) => setIp(e.target.value)}
          />
        </div>
        <div className="grid w-28 gap-1.5">
          <Label htmlFor={`${id}-port`}>Port</Label>
          <Input
            id={`${id}-port`}
            name="port"
            type="number"
            required
            min={1}
            max={65535}
            className="font-mono"
            value={port}
            onChange={(e) => setPort(e.target.value)}
          />
        </div>
        <Button type="submit" variant="outline" disabled={enCours}>
          Ajouter
        </Button>
      </div>
      {enCours && <output className="text-muted-foreground">Recherche du Flux…</output>}
      {erreur && (
        <p role="alert" className="text-13 text-destructive">
          {erreur}
        </p>
      )}
    </form>
  );
}

type PropsCandidats = Readonly<{
  resultat: ResultatDetection;
  onglet: Onglet;
  onOnglet: (onglet: Onglet) => void;
  /** Clé du Candidat dont le panneau d'ajout est ouvert sous sa ligne. */
  enAjout: string | null;
  onOuvrir: (candidat: Candidat) => void;
  onFermer: () => void;
  onAjoutee: (candidat: Candidat, camera: Camera) => void;
}>;

/**
 * « Filtrer par MAC », puis deux onglets avec leur compteur : les nouveaux Candidats, chacun avec « Ajouter »
 * (le panneau d'ajout s'ouvre sous sa ligne), et ceux déjà configurés avec le nom de leur Caméra.
 * L'onglet Candidats reste monté quand l'autre est choisi : changer d'onglet ne ferme pas un Aperçu.
 */
function Candidats({ resultat, onglet, onOnglet, enAjout, onOuvrir, onFermer, onAjoutee }: PropsCandidats) {
  const id = useId();
  const [filtre, setFiltre] = useState("");
  const filtreSaisi = filtre.trim() !== "";
  const invalide = filtreMacInvalide(filtre);
  // Le Candidat en cours d'ajout reste affiché : le masquer fermerait son Aperçu.
  const retenus = new Set(filtrerParMac(resultat.candidats, filtre));
  const filtres = resultat.candidats.filter((candidat) => retenus.has(candidat) || enAjout === cle(candidat));
  const nouveaux = filtres.filter((candidat) => candidat.camera === null);
  const configures = filtres.filter((candidat) => candidat.camera !== null);
  const nouveauxDetectes = resultat.candidats.some((candidat) => candidat.camera === null);
  const configuresDetectes = resultat.candidats.some((candidat) => candidat.camera !== null);

  /** Onglet vide : le filtre qui a tout masqué, ou rien de détecté. Filtre invalide : dit sous le champ. */
  function vide(detectes: boolean, sansFiltre: string) {
    if (filtreSaisi && detectes) return invalide ? null : <Vide>{SANS_CORRESPONDANCE}</Vide>;
    return <Vide>{sansFiltre}</Vide>;
  }

  return (
    <div className="grid gap-4">
      {resultat.candidats.length > 0 && (
        <div className="grid max-w-sm gap-1.5">
          <Label htmlFor={`${id}-filtre`}>Filtrer par MAC</Label>
          <Input
            id={`${id}-filtre`}
            autoComplete="off"
            spellCheck={false}
            placeholder="AA-BB-CC-DD-EE-FF"
            className="font-mono"
            value={filtre}
            aria-invalid={invalide ? true : undefined}
            aria-describedby={invalide ? `${id}-filtre-erreur` : undefined}
            onChange={(e) => setFiltre(e.target.value)}
          />
          {invalide && (
            <p id={`${id}-filtre-erreur`} role="alert" className="text-13 text-destructive">
              {MAC_INVALIDE}
            </p>
          )}
        </div>
      )}
      <Tabs value={onglet} onValueChange={(valeur) => onOnglet(valeur as Onglet)}>
        <TabsList>
          <TabsTrigger value="candidats">Candidats ({nouveaux.length})</TabsTrigger>
          <TabsTrigger value="deja">Déjà configurées ({configures.length})</TabsTrigger>
        </TabsList>
        <TabsContent value="candidats" forceMount className="data-[state=inactive]:hidden">
          {nouveaux.length === 0 &&
            vide(
              nouveauxDetectes,
              `Aucun ${configuresDetectes ? "nouveau " : ""}Candidat sur ${couverture(resultat.sous_reseaux, resultat.ports)}.`,
            )}
          {nouveaux.length > 0 && (
            <div className="rounded-lg border">
              <Table aria-label="Candidats">
                <EnTete colonnes={["IP", "Port", "MAC", "Actions"]} />
                <TableBody>
                  {nouveaux.map((candidat) => (
                    <Fragment key={cle(candidat)}>
                      <TableRow>
                        <Adresses candidat={candidat} />
                        <TableCell className="text-right">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={enAjout === cle(candidat)}
                            onClick={() => onOuvrir(candidat)}
                          >
                            Ajouter
                          </Button>
                        </TableCell>
                      </TableRow>
                      {enAjout === cle(candidat) && (
                        <TableRow className="hover:bg-transparent">
                          <TableCell colSpan={4} className="bg-background/40">
                            <AjoutCandidat
                              candidat={candidat}
                              onAjoutee={(camera) => onAjoutee(candidat, camera)}
                              onFermer={onFermer}
                            />
                          </TableCell>
                        </TableRow>
                      )}
                    </Fragment>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>
        <TabsContent value="deja">
          {configures.length === 0 && vide(configuresDetectes, "Aucune Caméra déjà configurée parmi les Candidats.")}
          {configures.length > 0 && (
            <div className="rounded-lg border">
              <Table aria-label="Déjà configurées">
                <EnTete colonnes={["IP", "Port", "MAC", "Caméra"]} />
                <TableBody>
                  {configures.map((candidat) => (
                    <TableRow key={cle(candidat)}>
                      <Adresses candidat={candidat} />
                      <TableCell>
                        <div className="font-medium">{candidat.camera?.nom}</div>
                        <Suivi candidat={candidat} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function EnTete({ colonnes }: Readonly<{ colonnes: string[] }>) {
  return (
    <TableHeader>
      <TableRow className="hover:bg-transparent">
        {colonnes.map((colonne) => (
          <TableHead key={colonne} className={colonne === "Actions" ? "text-right" : undefined}>
            {colonne}
          </TableHead>
        ))}
      </TableRow>
    </TableHeader>
  );
}

/** Cellules IP, Port et MAC d'un Candidat. */
function Adresses({ candidat }: Readonly<{ candidat: Candidat }>) {
  return (
    <>
      <TableCell className="font-mono text-xs">{candidat.ip}</TableCell>
      <TableCell className="font-mono text-xs">{candidat.port}</TableCell>
      <TableCell className="font-mono text-xs">{texteMac(candidat.mac)}</TableCell>
    </>
  );
}

function Vide({ children }: Readonly<{ children: string }>) {
  return <p className="rounded-lg border border-dashed p-6 text-center text-muted-foreground">{children}</p>;
}

/** Ce que la Détection a fait de l'adresse d'un Appareil connu vu à une autre IP. */
function Suivi({ candidat }: Readonly<{ candidat: Candidat }>) {
  const { adresse_mise_a_jour: adresse, conflit } = candidat;
  if (conflit) {
    return <div className="text-xs text-destructive">adresse non mise à jour : URL déjà prise par {conflit.nom}</div>;
  }
  if (adresse) {
    return (
      <div className="text-xs text-muted-foreground">
        adresse mise à jour ({adresse.ancienne} → {adresse.nouvelle})
      </div>
    );
  }
  return null;
}
