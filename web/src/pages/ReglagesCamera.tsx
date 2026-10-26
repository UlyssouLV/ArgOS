import { useEffect, useId, useState, type FormEvent, type ReactNode } from "react";
import { ChevronDown, Trash2 } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Sheet, SheetContent, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { notifier } from "@/notifier";
import {
  LONGUEUR_MOT_DE_PASSE_SUR,
  messageEchec,
  modifierCamera,
  Refus,
  supprimerCamera,
  type Camera,
  type SaisieCamera,
} from "../cameras";
import { LecteurFlux } from "../LecteurFlux";
import {
  accepterEnClair,
  COINS,
  COMPENSATION,
  COMPENSATIONS_IMAGE,
  empreinteCourte,
  empreinteGroupee,
  encodageHorsBornes,
  estVide,
  faireConfiance,
  INFRAROUGE,
  lireReglages,
  modificationsEntre,
  modifierReglages,
  oublierCertificat,
  PARAMETRES_IMAGE,
  pasDe,
  RefusOnvif,
  saisieDepuis,
  textePosition,
  texteResolution,
  type Bornes,
  type CertificatsCompares,
  type ChampEncodage,
  type ChampImage,
  type ChampModifie,
  type CleIncrustation,
  type IncrustationSaisie,
  type ModeCompensation,
  type ModeInfrarouge,
  type ParametreImage,
  type Position,
  type Reglages,
  type ReglagesLus,
  type Saisie,
  type SaisieEncodage,
  type SecuriteOnvif,
  type ValeursImage,
} from "../reglages";

type Props = Readonly<{
  camera: Camera;
  onFermer: () => void;
  /** Relit la liste des Caméras après une modification ou une suppression. */
  onModifiee: () => Promise<void>;
}>;

/**
 * Réglages de la Caméra dans un panneau latéral droit (`dialog` « Réglages de <nom> »), non modal : la liste reste
 * lisible et utilisable derrière (« Réglages » d'une autre ligne y passe). Seuls Fermer et Échap le ferment.
 */
export function ReglagesCamera({ camera, onFermer, onModifiee }: Props) {
  return (
    <Sheet open modal={false} onOpenChange={(ouvert) => !ouvert && onFermer()}>
      <SheetContent
        className="w-full gap-0 sm:max-w-xl"
        aria-describedby={undefined}
        onInteractOutside={(evenement) => evenement.preventDefault()}
      >
        <PanneauReglages key={camera.id} camera={camera} onFermer={onFermer} onModifiee={onModifiee} />
      </SheetContent>
    </Sheet>
  );
}

/** Champs de la section Général, tels que saisis. */
type Generaux = { nom: string; url_rtsp: string; emplacement: string; active: boolean; enregistrement: boolean };

type ErreursGenerales = Partial<Record<"nom" | "url_rtsp", string>>;

function generauxDe(camera: Camera): Generaux {
  return {
    nom: camera.nom,
    url_rtsp: camera.url_rtsp,
    emplacement: camera.emplacement ?? "",
    active: camera.active,
    enregistrement: camera.enregistrement,
  };
}

/** Ce que la saisie change à la Caméra ; vide si rien. L'URL masquée renvoyée telle quelle garde le mot de passe. */
function modificationGenerale(
  camera: Camera,
  saisis: Partial<Generaux>,
): Partial<SaisieCamera & { active: boolean; enregistrement: boolean }> {
  const avant = generauxDe(camera);
  const modification: Partial<SaisieCamera & { active: boolean; enregistrement: boolean }> = {};
  if (saisis.nom !== undefined && saisis.nom !== avant.nom) modification.nom = saisis.nom.trim();
  if (saisis.url_rtsp !== undefined && saisis.url_rtsp !== avant.url_rtsp) modification.url_rtsp = saisis.url_rtsp.trim();
  if (saisis.emplacement !== undefined && saisis.emplacement.trim() !== avant.emplacement)
    modification.emplacement = saisis.emplacement.trim() || null;
  if (saisis.active !== undefined && saisis.active !== avant.active) modification.active = saisis.active;
  if (saisis.enregistrement !== undefined && saisis.enregistrement !== avant.enregistrement)
    modification.enregistrement = saisis.enregistrement;
  return modification;
}

/** Formulaire des Réglages ONVIF, une fois lus : valeurs d'origine (à l'ouverture), dernières relues, saisie, statuts. */
type FormulaireOnvif = {
  origine: Reglages;
  actuels: Reglages;
  saisie: Saisie;
  statuts: Record<string, ChampModifie>;
};

/**
 * Général (nom, URL RTSP, emplacement, Caméra active, enregistrement) se règle pour ArgOS ; Image, Encodage et
 * Incrustation se lisent sur la caméra par ONVIF à l'ouverture d'une Caméra active ; ONVIF montre la sécurité de
 * l'échange et les décisions qu'elle demande (certificat changé, HTTPS disparu, ONVIF en clair), qui relisent la
 * caméra. « Appliquer » n'envoie que ce qui diffère, résultat en toast et statut sous chaque champ ONVIF envoyé ;
 * « Annuler » revient aux valeurs d'origine. Le Flux se lit en tête, pour voir l'effet d'un réglage ; fermer le
 * panneau arrête la lecture.
 */
function PanneauReglages({ camera, onFermer, onModifiee }: Props) {
  const [saisis, setSaisis] = useState<Partial<Generaux>>({});
  const [erreurs, setErreurs] = useState<ErreursGenerales>({});
  const [lus, setLus] = useState<ReglagesLus | null>(null);
  const [echec, setEchec] = useState<unknown>(null);
  // Incrémentée après une décision sur le certificat ou l'ONVIF en clair : relit la caméra.
  const [lecture, setLecture] = useState(0);
  const [formulaire, setFormulaire] = useState<FormulaireOnvif | null>(null);
  const [aCacher, setACacher] = useState<CleIncrustation | null>(null);
  const [coupure, setCoupure] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [onvifOuverte, setOnvifOuverte] = useState(false);

  useEffect(() => {
    if (!camera.active) return;
    let ouvert = true;
    lireReglages(camera.id).then(
      (origine) => {
        if (!ouvert) return;
        setLus(origine);
        setFormulaire({ origine, actuels: origine, saisie: saisieDepuis(origine), statuts: {} });
      },
      (e: unknown) => {
        if (!ouvert) return;
        setEchec(e ?? new Error());
        // Une décision ou un échec se lit sans avoir à déplier la section.
        setOnvifOuverte(true);
      },
    );
    return () => {
      ouvert = false;
    };
  }, [camera.id, camera.active, lecture]);

  function relire() {
    setLus(null);
    setFormulaire(null);
    setEchec(null);
    setLecture((n) => n + 1);
  }

  const generaux = { ...generauxDe(camera), ...saisis };
  const modificationCamera = modificationGenerale(camera, saisis);
  const modification = formulaire && modificationsEntre(formulaire.actuels, formulaire.saisie);
  const horsBornes = formulaire ? encodageHorsBornes(formulaire.actuels.encodage, formulaire.saisie.encodage) : [];
  const rienAEnvoyer = Object.keys(modificationCamera).length === 0 && (!modification || estVide(modification));

  function saisirGeneral(champs: Partial<Generaux>) {
    setSaisis((avant) => ({ ...avant, ...champs }));
    setErreurs((avant) => {
      const restantes = { ...avant };
      for (const champ of Object.keys(champs)) delete restantes[champ as keyof ErreursGenerales];
      return restantes;
    });
  }

  function saisirOnvif(changer: (saisie: Saisie) => Saisie) {
    setFormulaire((avant) => avant && { ...avant, saisie: changer(avant.saisie) });
  }

  function annuler() {
    setSaisis({});
    setErreurs({});
    setFormulaire((avant) => avant && { ...avant, saisie: saisieDepuis(avant.origine), statuts: {} });
    setACacher(null);
    setCoupure(false);
  }

  /** Erreur rattachée au champ en cause : URL refusée (422), nom ou URL déjà pris (409). */
  function erreurDeSaisie(e: unknown): ErreursGenerales | null {
    if (!(e instanceof Refus) || e instanceof RefusOnvif) return null;
    if (e.statut === 422) return { url_rtsp: e.message };
    if (e.statut === 409) return modificationCamera.nom === undefined ? { url_rtsp: e.message } : { nom: e.message };
    return null;
  }

  async function appliquer() {
    setCoupure(false);
    if (modificationCamera.nom !== undefined && !modificationCamera.nom) {
      setErreurs({ nom: "Le nom est obligatoire." });
      return;
    }
    if (modificationCamera.url_rtsp !== undefined && !modificationCamera.url_rtsp) {
      setErreurs({ url_rtsp: "L'URL RTSP est obligatoire." });
      return;
    }
    setEnvoi(true);
    const nom = modificationCamera.nom ?? camera.nom;
    try {
      let nonPris = false;
      // ONVIF d'abord : il demande une Caméra active, que Général peut désactiver.
      if (formulaire && modification && !estVide(modification)) {
        const resultat = await modifierReglages(camera.id, modification);
        setFormulaire({
          ...formulaire,
          actuels: resultat.reglages,
          statuts: Object.fromEntries(resultat.champs.map((champ) => [champ.champ, champ])),
        });
        nonPris = resultat.champs.some((champ) => champ.statut !== "pris" || champ.raison === "sans_reponse");
      }
      if (Object.keys(modificationCamera).length > 0) {
        try {
          await modifierCamera(camera.id, modificationCamera);
        } catch (e) {
          setErreurs(erreurDeSaisie(e) ?? {});
          throw e;
        }
        setSaisis({});
        await onModifiee();
      }
      if (nonPris) notifier(`Réglages de ${nom} envoyés : certains n'ont pas été pris par la caméra.`, "echec");
      else notifier(`Réglages de ${nom} appliqués.`);
    } catch (e) {
      const message = messageEchec(e);
      if (message) notifier(`Réglages non appliqués : ${message}`, "echec");
    } finally {
      setEnvoi(false);
    }
  }

  function valider(evenement: FormEvent) {
    evenement.preventDefault();
    // L'Encodage coupe le Flux quelques secondes : confirmé avant l'envoi, pas le reste.
    if (modification?.encodage) setCoupure(true);
    else void appliquer();
  }

  const refus = echec instanceof RefusOnvif ? echec : null;
  // Certificat changé, HTTPS indisponible et ONVIF en clair non accepté ont leur écran ; les autres échecs, leur message.
  const decision =
    refus?.code === "certificat_change" || refus?.code === "https_indisponible" || refus?.code === "en_clair_non_accepte";
  const erreur = echec === null || decision ? null : messageEchec(echec);

  return (
    <>
      <SheetHeader className="border-b pr-12">
        <SheetTitle className="text-base">Réglages de {camera.nom}</SheetTitle>
        <p className="font-mono text-xs text-muted-foreground">
          {camera.hote}:{camera.port}
        </p>
      </SheetHeader>
      <form noValidate onSubmit={valider} className="flex min-h-0 flex-1 flex-col">
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {/* Une clé par Flux, comme le Live : un autre Flux démonte le lecteur, qui ferme sa connexion. */}
          {camera.chemin_flux && (
            <LecteurFlux
              key={camera.chemin_flux}
              cheminFlux={camera.chemin_flux}
              codec={camera.codec}
              className="overflow-hidden rounded-md"
            />
          )}
          <Section titre="Général" defaultOpen>
            <ChampsGeneraux camera={camera} generaux={generaux} erreurs={erreurs} onChanger={saisirGeneral} />
          </Section>
          {!camera.active && (
            <p className="rounded-md border border-dashed p-3 text-13 text-muted-foreground">
              Caméra désactivée : Image, Encodage, Incrustation et ONVIF se lisent sur la caméra quand elle est active.
            </p>
          )}
          {camera.active && !lus && echec === null && (
            <div className="space-y-2" aria-busy="true">
              <p className="text-13 text-muted-foreground">Lecture de la caméra…</p>
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          )}
          {camera.active && formulaire && (
            <>
              <Section titre="Image">
                <ChampsImage
                  origine={formulaire.origine.image.valeurs}
                  actuels={formulaire.actuels}
                  saisie={formulaire.saisie.image}
                  statuts={formulaire.statuts}
                  onChanger={(champs) =>
                    saisirOnvif((avant) => ({ ...avant, image: avant.image && { ...avant.image, ...champs } }))
                  }
                />
              </Section>
              <Section titre="Encodage">
                <ChampsEncodage
                  origine={formulaire.origine.encodage}
                  actuels={formulaire.actuels}
                  saisie={formulaire.saisie.encodage}
                  horsBornes={horsBornes}
                  statuts={formulaire.statuts}
                  onChanger={(champs) =>
                    saisirOnvif((avant) => ({
                      ...avant,
                      encodage: avant.encodage && { ...avant.encodage, ...champs },
                    }))
                  }
                />
              </Section>
              <Section titre="Incrustation">
                <ChampsIncrustations
                  formulaire={formulaire}
                  aCacher={aCacher}
                  nomArgos={camera.nom}
                  onACacher={setACacher}
                  onChanger={saisirOnvif}
                />
              </Section>
            </>
          )}
          {camera.active && (lus || echec !== null) && (
            <Section titre="ONVIF" open={onvifOuverte} onOpenChange={setOnvifOuverte}>
              {refus?.code === "certificat_change" && (
                <CertificatChange camera={camera} message={refus.message} certificat={refus.certificat} onDecide={relire} />
              )}
              {refus?.code === "https_indisponible" && (
                <HttpsIndisponible camera={camera} message={refus.message} onDecide={relire} />
              )}
              {refus?.code === "en_clair_non_accepte" && (
                <AccordEnClair camera={camera} message={refus.message} onDecide={relire} />
              )}
              {erreur && <Erreur>{erreur}</Erreur>}
              {lus && <BandeauSecurite camera={camera} securite={lus.securite} onDecide={relire} />}
            </Section>
          )}
          <SuppressionCamera camera={camera} onFermer={onFermer} onModifiee={onModifiee} />
        </div>
        {coupure && (
          <Confirmation texte="Le Flux de cette Caméra sera coupé quelques secondes." className="mx-4 mb-3">
            <Button type="button" variant="destructive" size="sm" onClick={() => void appliquer()}>
              Couper le Flux et appliquer
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => setCoupure(false)}>
              Garder le Flux
            </Button>
          </Confirmation>
        )}
        <SheetFooter className="flex-row justify-end border-t">
          <Button type="button" variant="outline" disabled={envoi} onClick={annuler}>
            Annuler
          </Button>
          <Button type="submit" disabled={envoi || coupure || rienAEnvoyer || horsBornes.length > 0}>
            {envoi ? "Envoi…" : "Appliquer"}
          </Button>
        </SheetFooter>
      </form>
    </>
  );
}

/** Section repliable du panneau, nommée par son titre (rôle `region`). */
function Section({
  titre,
  children,
  ...etat
}: Readonly<{
  titre: string;
  children: ReactNode;
  defaultOpen?: boolean;
  open?: boolean;
  onOpenChange?: (ouverte: boolean) => void;
}>) {
  const id = useId();
  return (
    <Collapsible {...etat} asChild>
      <section aria-labelledby={id} className="rounded-lg border bg-background/40">
        <h3>
          <CollapsibleTrigger
            id={id}
            className="group flex w-full items-center justify-between rounded-lg px-4 py-3 text-sm font-semibold anneau-focus hover:bg-accent/60"
          >
            {titre}
            <ChevronDown
              className="size-4 text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
              aria-hidden="true"
            />
          </CollapsibleTrigger>
        </h3>
        <CollapsibleContent className="space-y-4 border-t px-4 py-4">{children}</CollapsibleContent>
      </section>
    </Collapsible>
  );
}

/** Champ du panneau : libellé, contrôle, puis valeur d'origine, statut de l'envoi et erreur de saisie dessous. */
function Champ({
  id,
  libelle,
  children,
  dessous,
}: Readonly<{ id: string; libelle: string; children: ReactNode; dessous?: ReactNode }>) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{libelle}</Label>
      {children}
      {dessous && <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs">{dessous}</div>}
    </div>
  );
}

function Erreur({ children, id }: Readonly<{ children: ReactNode; id?: string }>) {
  return (
    <p id={id} role="alert" className="text-13 text-destructive">
      {children}
    </p>
  );
}

function Avertissement({ children }: Readonly<{ children: ReactNode }>) {
  return <p className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-13">{children}</p>;
}

/** Demande de confirmation sur place : le texte, puis les deux choix. */
function Confirmation({ texte, children, className }: Readonly<{ texte: string; children: ReactNode; className?: string }>) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2 rounded-md border bg-accent p-3 text-13", className)}>
      <span className="mr-auto">{texte}</span>
      {children}
    </div>
  );
}

function ChampsGeneraux({
  camera,
  generaux,
  erreurs,
  onChanger,
}: Readonly<{
  camera: Camera;
  generaux: Generaux;
  erreurs: ErreursGenerales;
  onChanger: (champs: Partial<Generaux>) => void;
}>) {
  const id = useId();
  const champTexte = (champ: "nom" | "url_rtsp" | "emplacement", libelle: string, placeholder?: string) => {
    const erreur = champ === "emplacement" ? undefined : erreurs[champ];
    return (
      <Champ
        id={`${id}-${champ}`}
        libelle={libelle}
        dessous={erreur && <Erreur id={`${id}-${champ}-erreur`}>{erreur}</Erreur>}
      >
        <Input
          id={`${id}-${champ}`}
          name={champ}
          placeholder={placeholder}
          value={generaux[champ]}
          aria-invalid={erreur ? true : undefined}
          aria-describedby={erreur ? `${id}-${champ}-erreur` : undefined}
          className={champ === "url_rtsp" ? "font-mono text-xs" : undefined}
          onChange={(e) => onChanger({ [champ]: e.target.value })}
        />
      </Champ>
    );
  };

  return (
    <>
      {champTexte("nom", "Nom")}
      {/* En modification, l'URL masquée est renvoyée telle quelle si elle n'est pas touchée. */}
      {champTexte("url_rtsp", "URL RTSP", "rtsp://utilisateur:motdepasse@hote:554/chemin")}
      {champTexte("emplacement", "Emplacement", "facultatif")}
      <div className="flex items-center justify-between gap-4">
        <Label htmlFor={`${id}-active`}>Caméra active</Label>
        <Switch
          id={`${id}-active`}
          checked={generaux.active}
          onCheckedChange={(active) => onChanger({ active })}
        />
      </div>
      <div className="flex items-center justify-between gap-4">
        <Label htmlFor={`${id}-enregistrement`}>Enregistrement</Label>
        <Switch
          id={`${id}-enregistrement`}
          checked={generaux.enregistrement}
          disabled={!generaux.active}
          onCheckedChange={(enregistrement) => onChanger({ enregistrement })}
        />
      </div>
      <p className="font-mono text-xs text-muted-foreground">{camera.dossier_enregistrement}</p>
    </>
  );
}

/** « Supprimer la Caméra », confirmé par une boîte de dialogue ; seule une Caméra désactivée peut l'être. */
function SuppressionCamera({ camera, onFermer, onModifiee }: Props) {
  async function supprimer() {
    try {
      await supprimerCamera(camera.id);
      notifier(`Caméra ${camera.nom} supprimée.`);
      onFermer();
    } catch (e) {
      const message = messageEchec(e);
      if (message) notifier(`Suppression refusée : ${message}`, "echec");
    }
    await onModifiee();
  }

  return (
    <div className="space-y-2 border-t pt-4">
      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button
            type="button"
            variant="outline"
            disabled={camera.active}
            className="text-destructive hover:text-destructive"
          >
            <Trash2 />
            Supprimer la Caméra
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer {camera.nom} ?</AlertDialogTitle>
            <AlertDialogDescription>
              La Caméra et ses enregistrements sont supprimés définitivement.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction className={buttonVariants({ variant: "destructive" })} onClick={() => void supprimer()}>
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      {camera.active && (
        <p className="text-xs text-muted-foreground">Désactivez la Caméra (Général) pour pouvoir la supprimer.</p>
      )}
    </div>
  );
}

/**
 * Échange chiffré : empreinte courte du Certificat de l'Appareil (entière au survol) et sa date ; « TLS ancien ».
 * ONVIF en clair : rappel, et retrait de l'accord.
 */
function BandeauSecurite({
  camera,
  securite,
  onDecide,
}: Readonly<{ camera: Camera; securite: SecuriteOnvif; onDecide: () => void }>) {
  if (!securite.chiffre)
    return <BandeauEnClair camera={camera} motDePasseCourt={securite.mot_de_passe_court} onDecide={onDecide} />;
  return (
    <section className="space-y-2 text-13" aria-label="Sécurité de l'échange">
      <p>
        Échange chiffré (HTTPS).
        {securite.empreinte && (
          <>
            {" "}
            Certificat de l'Appareil <code className="font-mono text-xs" title={securite.empreinte}>
              {empreinteCourte(securite.empreinte)}
            </code>
            {securite.empreinte_memorisee_le &&
              `, mémorisé le ${new Date(securite.empreinte_memorisee_le).toLocaleDateString("fr-FR")}`}
            .
          </>
        )}
      </p>
      {securite.tls_ancien && (
        <Avertissement>
          TLS ancien : la caméra ne propose que TLS 1.0 ou 1.1, des versions dépassées. L'échange reste chiffré, avec la
          clé mémorisée.
        </Avertissement>
      )}
    </section>
  );
}

/** Décision de l'Administrateur envoyée à l'API, puis relecture ; l'échec reste affiché sur place. */
function useDecision(onDecide: () => void) {
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  async function decider(action: () => Promise<void>) {
    setEnvoi(true);
    setErreur(null);
    try {
      await action();
      onDecide();
    } catch (e) {
      setErreur(messageEchec(e));
    } finally {
      setEnvoi(false);
    }
  }

  return { envoi, erreur, decider };
}

/**
 * Réglages en ONVIF en clair, accepté par l'Administrateur : rappelé à chaque ouverture, et révocable.
 * Mot de passe court : rappelé aussi, puisque son empreinte passe en clair.
 */
function BandeauEnClair({
  camera,
  motDePasseCourt,
  onDecide,
}: Readonly<{ camera: Camera; motDePasseCourt: boolean; onDecide: () => void }>) {
  const { envoi, erreur, decider } = useDecision(onDecide);
  return (
    <section className="space-y-2" aria-label="Sécurité de l'échange">
      <Avertissement>
        ONVIF en clair : cette caméra ne propose pas HTTPS. Le mot de passe (en empreinte) et les réglages passent en
        clair sur le réseau des caméras.
      </Avertissement>
      {motDePasseCourt && (
        <Avertissement>
          Mot de passe court (moins de {LONGUEUR_MOT_DE_PASSE_SUR} caractères) : son empreinte (SHA-1, imposé par la
          norme), qui passe ici en clair, se casse hors ligne. Mieux vaut un mot de passe d'au moins{" "}
          {LONGUEUR_MOT_DE_PASSE_SUR} caractères, sur la caméra puis dans l'URL de la Caméra.
        </Avertissement>
      )}
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={envoi}
        onClick={() => void decider(() => accepterEnClair(camera.id, false))}
      >
        Retirer l'accord ONVIF en clair
      </Button>
      {erreur && <p className="text-13 text-destructive">{erreur}</p>}
    </section>
  );
}

type PropsRefus = Readonly<{ camera: Camera; message: string; onDecide: () => void }>;

/**
 * La caméra ne propose pas HTTPS : seule la recherche du port lui est parvenue. « Régler quand même en clair »
 * mémorise l'accord pour cette Caméra, révocable depuis le bandeau.
 */
function AccordEnClair({ camera, message, onDecide }: PropsRefus) {
  const { envoi, erreur, decider } = useDecision(onDecide);
  return (
    <section className="space-y-2 text-13" aria-label="ONVIF en clair">
      <Erreur>{message}</Erreur>
      <p>
        La régler quand même ferait passer son mot de passe (en empreinte, cassable hors ligne s'il est faible) et ses
        réglages en clair sur le réseau des caméras : qui l'écoute peut les lire ou les modifier au passage. Rien n'a
        été envoyé avec ses identifiants.
      </p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={envoi}
        onClick={() => void decider(() => accepterEnClair(camera.id, true))}
      >
        Régler quand même en clair
      </Button>
      {erreur && <p className="text-destructive">{erreur}</p>}
    </section>
  );
}

function texteEmpreinte(empreinte: string | null): string {
  return empreinte ? empreinteGroupee(empreinte) : "inconnu";
}

/**
 * La caméra présente une autre clé que celle mémorisée : rien d'authentifié n'est parti. Les deux empreintes et les
 * causes possibles ; « Faire confiance au nouveau certificat », confirmé, n'accepte que l'empreinte montrée ici.
 */
function CertificatChange({
  camera,
  message,
  certificat,
  onDecide,
}: PropsRefus & Readonly<{ certificat: CertificatsCompares | null }>) {
  const [confirmation, setConfirmation] = useState(false);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const presentee = certificat?.empreinte_presentee ?? null;

  async function confier(empreinte: string) {
    setEnvoi(true);
    setErreur(null);
    try {
      await faireConfiance(camera.id, empreinte);
      onDecide();
    } catch (e) {
      setErreur(messageEchec(e));
      setConfirmation(false);
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <section className="space-y-2 text-13" aria-label="Certificat changé">
      <Erreur>{message}</Erreur>
      <dl className="grid gap-1">
        <dt className="text-muted-foreground">Certificat mémorisé</dt>
        <dd>
          <code className="font-mono text-xs break-all">{texteEmpreinte(certificat?.empreinte_memorisee ?? null)}</code>
          {certificat?.empreinte_memorisee_le &&
            `, le ${new Date(certificat.empreinte_memorisee_le).toLocaleDateString("fr-FR")}`}
        </dd>
        <dt className="text-muted-foreground">Certificat présenté</dt>
        <dd>
          <code className="font-mono text-xs break-all">{texteEmpreinte(presentee)}</code>
        </dd>
      </dl>
      <p>
        Causes possibles : remise en usine, nouveau firmware, autre appareil à cette adresse. Rien n'est envoyé à la
        caméra avec ses identifiants tant que vous n'avez pas tranché.
      </p>
      {presentee && !confirmation && (
        <Button type="button" variant="outline" size="sm" disabled={envoi} onClick={() => setConfirmation(true)}>
          Faire confiance au nouveau certificat
        </Button>
      )}
      {presentee && confirmation && (
        <Confirmation
          texte={`ArgOS réglera cette caméra avec le certificat ${empreinteCourte(presentee)} et refusera l'ancien. Ne le faites que si vous savez pourquoi il a changé.`}
        >
          <Button
            type="button"
            variant="destructive"
            size="sm"
            disabled={envoi}
            onClick={() => void confier(presentee)}
          >
            Confirmer la confiance
          </Button>
          <Button type="button" variant="outline" size="sm" disabled={envoi} onClick={() => setConfirmation(false)}>
            Annuler
          </Button>
        </Confirmation>
      )}
      {erreur && <p className="text-destructive">{erreur}</p>}
    </section>
  );
}

/** La Caméra répondait en HTTPS et ne le fait plus : pas de repli en clair ; « Oublier le certificat » repart de zéro. */
function HttpsIndisponible({ camera, message, onDecide }: PropsRefus) {
  const { envoi, erreur, decider } = useDecision(onDecide);

  return (
    <section className="space-y-2 text-13" aria-label="HTTPS indisponible">
      <Erreur>{message}</Erreur>
      <p>
        Causes possibles : remise en usine, nouveau firmware, autre appareil à cette adresse, ou quelqu'un qui bloque
        HTTPS pour lire l'échange en clair. Oublier le certificat fait repartir le contact suivant de zéro.
      </p>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={envoi}
        onClick={() => void decider(() => oublierCertificat(camera.id))}
      >
        Oublier le certificat de cette caméra
      </Button>
      {erreur && <p className="text-destructive">{erreur}</p>}
    </section>
  );
}

// Libellés de chaque Incrustation : « Texte du nom », « Cacher la date et heure »…
const LIBELLES: Record<CleIncrustation, { titre: string; de: string; article: string }> = {
  nom: { titre: "Nom", de: "du nom", article: "le nom" },
  date_heure: {
    titre: "Date et heure",
    de: "de la date et heure",
    article: "la date et heure",
  },
};

/** Cacher une Incrustation affichée sur la caméra se confirme : certaines ne savent pas la recréer. */
function ChampsIncrustations({
  formulaire,
  aCacher,
  nomArgos,
  onACacher,
  onChanger,
}: Readonly<{
  formulaire: FormulaireOnvif;
  aCacher: CleIncrustation | null;
  nomArgos: string;
  onACacher: (cle: CleIncrustation | null) => void;
  onChanger: (changer: (saisie: Saisie) => Saisie) => void;
}>) {
  const { origine, actuels, saisie, statuts } = formulaire;

  function changer(cle: CleIncrustation, champs: Partial<IncrustationSaisie>) {
    onChanger((avant) => ({
      ...avant,
      incrustations: { ...avant.incrustations, [cle]: { ...avant.incrustations[cle], ...champs } },
    }));
  }

  return (
    <>
      {(["nom", "date_heure"] as const).map((cle) => (
        <ChampsIncrustation
          key={cle}
          cle={cle}
          origine={origine}
          actuels={actuels}
          saisie={saisie.incrustations[cle]}
          statuts={statuts}
          confirmation={aCacher === cle}
          nomArgos={nomArgos}
          onChanger={(champs) => changer(cle, champs)}
          onAffichage={(affichee) => {
            if (!affichee && actuels.incrustations[cle].affichee) onACacher(cle);
            else changer(cle, { affichee });
          }}
          onConfirmerCacher={(confirme) => {
            if (confirme) changer(cle, { affichee: false });
            onACacher(null);
          }}
        />
      ))}
    </>
  );
}

type PropsChamps = Readonly<{
  cle: CleIncrustation;
  origine: Reglages;
  actuels: Reglages;
  saisie: IncrustationSaisie;
  statuts: Record<string, ChampModifie>;
  confirmation: boolean;
  nomArgos: string;
  onChanger: (champs: Partial<IncrustationSaisie>) => void;
  onAffichage: (affichee: boolean) => void;
  onConfirmerCacher: (confirme: boolean) => void;
}>;

function ChampsIncrustation({
  cle,
  origine,
  actuels,
  saisie,
  statuts,
  confirmation,
  nomArgos,
  onChanger,
  onAffichage,
  onConfirmerCacher,
}: PropsChamps) {
  const { titre, de, article } = LIBELLES[cle];
  const id = useId();
  const lue = origine.incrustations[cle];
  // « Afficher » n'est proposé que si l'Incrustation l'est déjà ou si la caméra sait la recréer.
  const actuelle = actuels.incrustations[cle];
  const peutAfficher = actuelle.affichee || actuelle.peut_etre_reaffichee;
  const statut = (champ: string, libelle: string) => (
    <StatutChamp resultat={statuts[`incrustations.${cle}.${champ}`]} libelle={`${libelle} ${de}`} />
  );

  return (
    <fieldset className="space-y-3 rounded-md border p-3">
      <legend className="px-1 text-13 font-medium">{titre}</legend>
      <Champ
        id={`${id}-affichage`}
        libelle={`Affichage ${de}`}
        dessous={
          <>
            <Origine valeur={lue.affichee ? "affichée" : "cachée"} />
            {statut("affichee", "affichage")}
          </>
        }
      >
        <NativeSelect
          id={`${id}-affichage`}
          value={saisie.affichee ? "affichee" : "cachee"}
          onChange={(e) => onAffichage(e.target.value === "affichee")}
        >
          {(peutAfficher || saisie.affichee) && <option value="affichee">affichée</option>}
          <option value="cachee">cachée</option>
        </NativeSelect>
      </Champ>
      {confirmation && (
        <Confirmation texte="Certaines caméras ne permettent pas de la réafficher ensuite.">
          <Button type="button" variant="destructive" size="sm" onClick={() => onConfirmerCacher(true)}>
            Cacher {article}
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => onConfirmerCacher(false)}>
            Garder {article}
          </Button>
        </Confirmation>
      )}
      {cle === "nom" && (
        <Champ
          id={`${id}-texte`}
          libelle={`Texte ${de}`}
          dessous={
            <>
              <Origine valeur={origine.incrustations.nom.texte ?? "—"} />
              {statut("texte", "texte")}
            </>
          }
        >
          <div className="flex gap-2">
            <Input
              id={`${id}-texte`}
              type="text"
              value={saisie.texte}
              disabled={!saisie.affichee}
              onChange={(e) => onChanger({ texte: e.target.value })}
            />
            <Button
              type="button"
              variant="outline"
              disabled={!saisie.affichee}
              onClick={() => onChanger({ texte: nomArgos })}
            >
              Reprendre le nom ArgOS
            </Button>
          </div>
        </Champ>
      )}
      {cle === "date_heure" && (
        <p className="text-13 text-muted-foreground">
          Format : <span className="font-mono text-xs">{origine.incrustations.date_heure.format ?? "—"}</span>
        </p>
      )}
      <Champ
        id={`${id}-position`}
        libelle={`Position ${de}`}
        dessous={
          <>
            <Origine valeur={textePosition(lue.position)} />
            {statut("position", "position")}
          </>
        }
      >
        <NativeSelect
          id={`${id}-position`}
          value={saisie.position}
          disabled={!saisie.affichee}
          onChange={(e) => onChanger({ position: e.target.value as Position })}
        >
          {saisie.position === "Custom" && <option value="Custom">{textePosition("Custom")}</option>}
          {COINS.map((coin) => (
            <option key={coin} value={coin}>
              {textePosition(coin)}
            </option>
          ))}
        </NativeSelect>
      </Champ>
    </fieldset>
  );
}

// Libellés des champs d'Image : « Luminosité », « Statut : luminosité »…
const LIBELLES_IMAGE: Record<ChampImage, string> = {
  infrarouge: "Filtre infrarouge",
  luminosite: "Luminosité",
  contraste: "Contraste",
  saturation: "Saturation",
  nettete: "Netteté",
  contre_jour: "Contre-jour",
  contre_jour_niveau: "Niveau du contre-jour",
  wdr: "WDR",
  wdr_niveau: "Niveau du WDR",
};

type PropsImage = Readonly<{
  origine: ValeursImage | null;
  actuels: Reglages;
  saisie: ValeursImage | null;
  statuts: Record<string, ChampModifie>;
  onChanger: (champs: Partial<ValeursImage>) => void;
}>;

/**
 * Image de l'Appareil, partagée par ses Caméras : seuls les paramètres que la caméra propose, curseurs bornés par
 * elle, avec la valeur chiffrée et celle d'origine. Sans service image : « Image non réglable sur cette caméra ».
 */
function ChampsImage({ origine, actuels, saisie, statuts, onChanger }: PropsImage) {
  const id = useId();
  const options = actuels.image.options;
  if (!actuels.image.reglable || !options || !origine || !saisie) {
    return <p className="text-13 text-muted-foreground">Image non réglable sur cette caméra</p>;
  }
  const statut = (champ: ChampImage) => (
    <StatutChamp resultat={statuts[`image.${champ}`]} libelle={LIBELLES_IMAGE[champ].toLowerCase()} />
  );
  const curseur = (champ: ParametreImage | `${"contre_jour" | "wdr"}_niveau`, bornes: Bornes | null) => {
    const valeur = saisie[champ];
    if (!bornes || valeur === null) return null;
    return (
      <Champ
        key={champ}
        id={`${id}-${champ}`}
        libelle={LIBELLES_IMAGE[champ]}
        dessous={
          <>
            <Origine valeur={texteNombre(origine[champ])} />
            {statut(champ)}
          </>
        }
      >
        <div className="flex items-center gap-3">
          <input
            id={`${id}-${champ}`}
            type="range"
            className="flex-1 accent-primary"
            min={bornes.min}
            max={bornes.max}
            step={pasDe(bornes)}
            value={valeur}
            onChange={(e) => onChanger({ [champ]: Number(e.target.value) })}
          />
          {/* Pas d'`<output>` : son rôle implicite `status` le confondrait avec le statut d'un envoi. */}
          <span className="valeur-curseur w-10 text-right font-mono text-xs">{valeur}</span>
        </div>
      </Champ>
    );
  };

  return (
    <>
      <p className="text-13 text-muted-foreground">
        Partagée par les Caméras de cet Appareil : la régler ici la règle pour chacune.
      </p>
      {options.infrarouge && saisie.infrarouge && (
        <Champ
          id={`${id}-infrarouge`}
          libelle={LIBELLES_IMAGE.infrarouge}
          dessous={
            <>
              <Origine valeur={origine.infrarouge ? INFRAROUGE[origine.infrarouge] : "—"} />
              {statut("infrarouge")}
            </>
          }
        >
          <NativeSelect
            id={`${id}-infrarouge`}
            value={saisie.infrarouge}
            onChange={(e) => onChanger({ infrarouge: e.target.value as ModeInfrarouge })}
          >
            {options.infrarouge.map((mode) => (
              <option key={mode} value={mode}>
                {INFRAROUGE[mode]}
              </option>
            ))}
          </NativeSelect>
        </Champ>
      )}
      {PARAMETRES_IMAGE.map((champ) => curseur(champ, options[champ]))}
      {COMPENSATIONS_IMAGE.map((champ) => {
        const modes = options[champ];
        const mode = saisie[champ];
        if (!modes || !mode) return null;
        return (
          <div key={champ} className="space-y-4">
            <Champ
              id={`${id}-${champ}`}
              libelle={LIBELLES_IMAGE[champ]}
              dessous={
                <>
                  <Origine valeur={origine[champ] ? COMPENSATION[origine[champ]] : "—"} />
                  {statut(champ)}
                </>
              }
            >
              <NativeSelect
                id={`${id}-${champ}`}
                value={mode}
                onChange={(e) => onChanger({ [champ]: e.target.value as ModeCompensation })}
              >
                {modes.map((m) => (
                  <option key={m} value={m}>
                    {COMPENSATION[m]}
                  </option>
                ))}
              </NativeSelect>
            </Champ>
            {curseur(`${champ}_niveau`, options[`${champ}_niveau`])}
          </div>
        );
      })}
    </>
  );
}

// Libellés des champs d'Encodage réglables : « Résolution », « Statut : débit max »…
const LIBELLES_ENCODAGE: Record<ChampEncodage, string> = {
  resolution: "Résolution",
  images_par_seconde: "Images par seconde",
  debit_max: "Débit max (kbit/s)",
};

const STATUTS_ENCODAGE: Record<ChampEncodage, string> = {
  resolution: "résolution",
  images_par_seconde: "images par seconde",
  debit_max: "débit max",
};

type PropsEncodage = Readonly<{
  origine: Reglages["encodage"];
  actuels: Reglages;
  saisie: SaisieEncodage | null;
  horsBornes: ChampEncodage[];
  statuts: Record<string, ChampModifie>;
  onChanger: (champs: Partial<SaisieEncodage>) => void;
}>;

/**
 * Encodage du Flux (profil de l'URL RTSP) : résolution parmi celles proposées, images par seconde et débit dans les
 * bornes de la caméra ; codec, qualité et intervalle entre images clés en lecture seule. Non réglable : valeurs en
 * lecture seule, et pourquoi. Une valeur hors des bornes s'affiche sous son champ.
 */
function ChampsEncodage({ origine, actuels, saisie, horsBornes, statuts, onChanger }: PropsEncodage) {
  const id = useId();
  const encodage = actuels.encodage;
  const valeurs = encodage.valeurs;
  if (!valeurs) {
    return (
      <p className="text-13 text-muted-foreground">
        {encodage.raison === "profil_introuvable"
          ? "Encodage introuvable pour ce Flux"
          : "Encodage non réglable sur cette caméra"}
      </p>
    );
  }
  const options = encodage.options;
  const reglable = encodage.reglable && options && saisie;
  const statut = (champ: ChampEncodage) => (
    <StatutChamp resultat={statuts[`encodage.${champ}`]} libelle={STATUTS_ENCODAGE[champ]} />
  );
  const nombre = (champ: "images_par_seconde" | "debit_max") => {
    const bornes = options?.[champ];
    if (!reglable || !bornes) return null;
    const valeur = saisie[champ];
    const horsBorne = horsBornes.includes(champ);
    return (
      <Champ
        id={`${id}-${champ}`}
        libelle={LIBELLES_ENCODAGE[champ]}
        dessous={
          <>
            <Origine valeur={texteNombre(origine.valeurs?.[champ] ?? null)} />
            {horsBorne && (
              <span id={`${id}-${champ}-erreur`} className="text-destructive">
                hors des bornes de la caméra ({bornes.min} à {bornes.max})
              </span>
            )}
            {statut(champ)}
          </>
        }
      >
        <Input
          id={`${id}-${champ}`}
          type="number"
          min={bornes.min}
          max={bornes.max}
          step={pasDe(bornes)}
          value={Number.isNaN(valeur) ? "" : valeur}
          aria-invalid={horsBorne ? true : undefined}
          aria-describedby={horsBorne ? `${id}-${champ}-erreur` : undefined}
          onChange={(e) => onChanger({ [champ]: e.target.value === "" ? Number.NaN : Number(e.target.value) })}
        />
      </Champ>
    );
  };

  return (
    <>
      {!reglable && <p className="text-13 text-muted-foreground">Encodage non réglable sur cette caméra</p>}
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-13">
        <dt className="text-muted-foreground">Profil</dt>
        <dd className="font-mono text-xs">{encodage.profil ?? "—"}</dd>
        {!reglable && (
          <>
            <dt className="text-muted-foreground">Résolution</dt>
            <dd className="font-mono text-xs">{texteResolution(valeurs.resolution)}</dd>
            <dt className="text-muted-foreground">Images par seconde</dt>
            <dd className="font-mono text-xs">{texteNombre(valeurs.images_par_seconde)}</dd>
            <dt className="text-muted-foreground">Débit max (kbit/s)</dt>
            <dd className="font-mono text-xs">{texteNombre(valeurs.debit_max)}</dd>
          </>
        )}
        <dt className="text-muted-foreground">Codec</dt>
        <dd className="font-mono text-xs">{valeurs.codec}</dd>
        <dt className="text-muted-foreground">Qualité</dt>
        <dd className="font-mono text-xs">{texteNombre(valeurs.qualite)}</dd>
        <dt className="text-muted-foreground">Intervalle entre images clés</dt>
        <dd className="font-mono text-xs">{texteNombre(valeurs.intervalle_images_cles)}</dd>
      </dl>
      {reglable && (
        <>
          <Champ
            id={`${id}-resolution`}
            libelle={LIBELLES_ENCODAGE.resolution}
            dessous={
              <>
                <Origine valeur={origine.valeurs ? texteResolution(origine.valeurs.resolution) : "—"} />
                {statut("resolution")}
              </>
            }
          >
            <NativeSelect
              id={`${id}-resolution`}
              value={saisie.resolution}
              onChange={(e) => onChanger({ resolution: e.target.value })}
            >
              {options.resolutions.map((resolution) => (
                <option key={resolution} value={resolution}>
                  {texteResolution(resolution)}
                </option>
              ))}
            </NativeSelect>
          </Champ>
          {nombre("images_par_seconde")}
          {nombre("debit_max")}
        </>
      )}
    </>
  );
}

function texteNombre(valeur: number | null): string {
  return valeur === null ? "—" : String(valeur);
}

function Origine({ valeur }: Readonly<{ valeur: string }>) {
  return <span className="text-muted-foreground">d'origine : {valeur}</span>;
}

const STATUTS: Record<ChampModifie["statut"], string> = { pris: "pris", pas_pris: "pas pris", refuse: "refusé" };

const COULEURS_STATUT: Record<ChampModifie["statut"], string> = {
  pris: "text-success",
  pas_pris: "text-unknown",
  refuse: "text-destructive",
};

/** Statut d'un champ envoyé, avec la valeur demandée et celle relue sur la caméra ; rien s'il n'a pas été envoyé. */
function StatutChamp({ resultat, libelle }: Readonly<{ resultat: ChampModifie | undefined; libelle: string }>) {
  if (!resultat) return null;
  const { champ, demande, relu, statut } = resultat;
  if (resultat.raison === "sans_reponse") {
    return (
      <span role="status" aria-label={`Statut : ${libelle}`} className={COULEURS_STATUT.pas_pris}>
        pas pris — la caméra n'a pas répondu après l'envoi
      </span>
    );
  }
  return (
    <span role="status" aria-label={`Statut : ${libelle}`} className={COULEURS_STATUT[statut]}>
      {STATUTS[statut]} (demandé : {texteValeur(champ, demande)}, relu : {texteValeur(champ, relu)})
    </span>
  );
}

function texteValeur(champ: string, valeur: ChampModifie["relu"]): string {
  if (valeur === null) return "—";
  if (typeof valeur === "boolean") return valeur ? "affichée" : "cachée";
  if (typeof valeur === "number") return String(valeur);
  if (champ === "image.infrarouge") return INFRAROUGE[valeur as ModeInfrarouge];
  if (champ === "image.contre_jour" || champ === "image.wdr") return COMPENSATION[valeur as ModeCompensation];
  if (champ === "encodage.resolution") return texteResolution(valeur);
  return champ.endsWith(".position") ? textePosition(valeur as Position) : valeur;
}
