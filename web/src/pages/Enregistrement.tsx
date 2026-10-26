import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { HardDrive, TriangleAlert } from "lucide-react";
import { Link, useNavigate } from "react-router";

import { EnTeteDePage } from "@/components/EnTeteDePage";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { notifier } from "@/notifier";
import { messageEchec } from "../cameras";
import {
  CONSERVATION_MAX,
  HEURES_PAR_JOUR,
  MO,
  SEUIL_MIN_O,
  conservationSaisie,
  formaterConservation,
  formaterDebit,
  formaterDuree,
  formaterOctets,
  joursEtHeures,
  libelleEtatEnregistrement,
  libelleSourceDebit,
  libelleTenue,
  lireDebitsEcriture,
  lireEspaceEnregistrements,
  lireReglagesSite,
  modifierReglagesSite,
  signalerEspaceModifie,
  type DebitCamera,
  type DebitsEcriture,
  type EspaceEnregistrements,
  type ReglagesSite,
} from "../reglagesSite";

const ERREUR_CONSERVATION = `La Conservation va de 1 h à ${CONSERVATION_MAX / HEURES_PAR_JOUR} jours.`;
const SEUIL_MIN_MO = Math.round(SEUIL_MIN_O / MO);
const ERREUR_SEUIL = `Le seuil doit être un entier d’au moins ${SEUIL_MIN_MO} Mo.`;

// Pastille de l'état d'enregistrement, toujours suivie de son libellé.
const COULEURS_ETAT: Record<DebitCamera["etat_enregistrement"], string> = {
  enregistre: "bg-success",
  a_l_arret: "bg-unknown",
  en_erreur: "bg-destructive",
};

const COLONNES = ["Caméra", "État", "Débit", "Plus ancien Segment"];

/** Page Enregistrement : place libre, débit, Conservation et sa tenue, Réglages et Caméras (ADR 0012, ADR 0017). */
export function Enregistrement() {
  const [reglages, setReglages] = useState<ReglagesSite | null>(null);
  const [saisieJours, setSaisieJours] = useState("");
  const [saisieHeures, setSaisieHeures] = useState("");
  const [saisieSeuilMo, setSaisieSeuilMo] = useState("");
  const [erreurConservation, setErreurConservation] = useState<string | null>(null);
  const [erreurSeuil, setErreurSeuil] = useState<string | null>(null);
  const [espace, setEspace] = useState<EspaceEnregistrements | null>(null);
  const [debits, setDebits] = useState<DebitsEcriture | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [enCours, setEnCours] = useState(false);

  const montrerReglages = useCallback((lus: ReglagesSite) => {
    setReglages(lus);
    const decoupe = joursEtHeures(lus.conservation_h);
    setSaisieJours(String(decoupe.jours));
    setSaisieHeures(String(decoupe.heures));
    setSaisieSeuilMo(String(Math.round(lus.seuil_octets_libres / MO)));
  }, []);

  const relireEspaceEtDebits = useCallback(async () => {
    const [espaceLu, debitsLus] = await Promise.all([lireEspaceEnregistrements(), lireDebitsEcriture()]);
    setEspace(espaceLu);
    setDebits(debitsLus);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const [lus] = await Promise.all([lireReglagesSite(), relireEspaceEtDebits()]);
        montrerReglages(lus);
        setErreur(null);
      } catch (e) {
        setErreur(messageEchec(e));
      }
    })();
  }, [montrerReglages, relireEspaceEtDebits]);

  async function enregistrer(event: FormEvent) {
    event.preventDefault();
    if (reglages === null) return;
    const heures = conservationSaisie(saisieJours, saisieHeures);
    const mo = Number(saisieSeuilMo);
    const seuilValide = Number.isInteger(mo) && mo >= SEUIL_MIN_MO;
    setErreurConservation(heures === null ? ERREUR_CONSERVATION : null);
    setErreurSeuil(seuilValide ? null : ERREUR_SEUIL);
    if (heures === null || !seuilValide) return;

    const champs = {
      ...(heures === reglages.conservation_h ? {} : { conservation_h: heures }),
      ...(mo * MO === reglages.seuil_octets_libres ? {} : { seuil_octets_libres: mo * MO }),
    };
    if (Object.keys(champs).length === 0) {
      montrerReglages(reglages);
      return;
    }
    setEnCours(true);
    try {
      montrerReglages(await modifierReglagesSite(champs));
      signalerEspaceModifie();
      notifier("Réglages d’enregistrement enregistrés.");
      await relireEspaceEtDebits();
    } catch (e) {
      const message = messageEchec(e);
      if (message) notifier(message, "echec");
    } finally {
      setEnCours(false);
    }
  }

  const heuresSaisies = conservationSaisie(saisieJours, saisieHeures);
  const inchanges =
    reglages !== null &&
    heuresSaisies === reglages.conservation_h &&
    saisieSeuilMo === String(Math.round(reglages.seuil_octets_libres / MO));
  // Même couple libre / seuil que l’écran affiche (évite un décalage avec `espace.sous_seuil` seul).
  const sousSeuil = espace !== null && reglages !== null && espace.libre_o < reglages.seuil_octets_libres;

  return (
    <>
      <EnTeteDePage titre="Enregistrement" />
      <div className="flex flex-col gap-6 p-6">
        {erreur && (
          <Alert variant="destructive">
            <AlertDescription>{erreur}</AlertDescription>
          </Alert>
        )}
        {sousSeuil && (
          <Alert variant="destructive" role="status">
            <TriangleAlert aria-hidden="true" />
            <AlertDescription>
              Place libre sous le seuil : l’enregistrement continue, agissez si besoin (réduire la Conservation ou
              couper des Caméras).
            </AlertDescription>
          </Alert>
        )}
        <div className="grid gap-4 lg:grid-cols-3">
          <CartePlaceLibre espace={espace} seuilO={reglages?.seuil_octets_libres ?? null} />
          <CarteDebit debits={debits} />
          <CarteConservation heures={reglages?.conservation_h ?? null} debits={debits} />
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Réglages</CardTitle>
            <CardDescription>
              Communs à toutes les Caméras. L’interrupteur d’enregistrement de chaque Caméra reste dans
              Administration › Caméras.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="grid gap-6 lg:grid-cols-2"
              aria-label="Réglages d’enregistrement"
              noValidate
              onSubmit={(e) => void enregistrer(e)}
            >
              <fieldset className="grid content-start gap-1.5" disabled={reglages === null || enCours}>
                <legend className="mb-1.5 text-sm font-medium">Conservation</legend>
                <div className="flex gap-3">
                  <ChampNombre
                    id="conservation-jours"
                    libelle="Jours"
                    discret
                    valeur={saisieJours}
                    surChangement={setSaisieJours}
                    erreur={erreurConservation}
                    idErreur="erreur-conservation"
                  />
                  <ChampNombre
                    id="conservation-heures"
                    libelle="Heures"
                    discret
                    valeur={saisieHeures}
                    surChangement={setSaisieHeures}
                    erreur={erreurConservation}
                    idErreur="erreur-conservation"
                  />
                </div>
                <MessageChamp id="erreur-conservation" erreur={erreurConservation}>
                  Durée pendant laquelle le Site garde les Segments, de 1 h à 30 jours.
                </MessageChamp>
              </fieldset>
              <fieldset className="grid content-start gap-1.5" disabled={reglages === null || enCours}>
                <ChampNombre
                  id="seuil-mo"
                  libelle="Seuil de place disque (Mo)"
                  valeur={saisieSeuilMo}
                  surChangement={setSaisieSeuilMo}
                  erreur={erreurSeuil}
                  idErreur="erreur-seuil"
                />
                <MessageChamp id="erreur-seuil" erreur={erreurSeuil}>
                  Marge d’octets libres sous laquelle un signal apparaît (plancher {SEUIL_MIN_MO} Mo, défaut 1024 Mo).
                  Aucune coupure automatique.
                </MessageChamp>
              </fieldset>
              <div>
                <Button type="submit" disabled={reglages === null || inchanges || enCours}>
                  Enregistrer
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
        <section className="flex flex-col gap-3" aria-labelledby="titre-cameras-enregistrement">
          <div>
            <h2 id="titre-cameras-enregistrement" className="text-base font-semibold">
              Caméras
            </h2>
            <p className="text-13 text-muted-foreground">Une ligne ouvre la Relecture de la Caméra.</p>
          </div>
          {debits === null && !erreur && <Squelettes libelle="Chargement des Caméras" lignes={3} />}
          {debits?.cameras.length === 0 && <AucuneCamera />}
          {debits && debits.cameras.length > 0 && (
            <div className="rounded-lg border bg-card">
              <Table aria-label="Débits par Caméra">
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    {COLONNES.map((colonne) => (
                      <TableHead key={colonne}>{colonne}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {debits.cameras.map((camera) => (
                    <LigneCamera key={camera.id} camera={camera} />
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

function ChampNombre({
  id,
  libelle,
  valeur,
  surChangement,
  erreur,
  idErreur,
  discret = false,
}: Readonly<{
  id: string;
  libelle: string;
  discret?: boolean;
  valeur: string;
  surChangement: (valeur: string) => void;
  erreur: string | null;
  idErreur: string;
}>) {
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} className={cn(discret && "text-13 text-muted-foreground")}>
        {libelle}
      </Label>
      <Input
        id={id}
        type="number"
        inputMode="numeric"
        min={0}
        step={1}
        className="w-28 font-mono"
        value={valeur}
        onChange={(e) => surChangement(e.target.value)}
        aria-invalid={erreur ? true : undefined}
        aria-describedby={idErreur}
      />
    </div>
  );
}

/** Aide du champ, remplacée par l'erreur de saisie quand il y en a une. */
function MessageChamp({ id, erreur, children }: Readonly<{ id: string; erreur: string | null; children: ReactNode }>) {
  return (
    <p id={id} className={cn("text-13", erreur ? "text-destructive" : "text-muted-foreground")}>
      {erreur ?? children}
    </p>
  );
}

function CarteChiffre({ titre, children }: Readonly<{ titre: string; children: ReactNode }>) {
  return (
    <Card className="gap-4" role="region" aria-label={titre}>
      <CardHeader>
        <CardTitle className="text-13 font-medium text-muted-foreground">{titre}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3">{children}</CardContent>
    </Card>
  );
}

function CartePlaceLibre({ espace, seuilO }: Readonly<{ espace: EspaceEnregistrements | null; seuilO: number | null }>) {
  if (espace === null || seuilO === null) {
    return (
      <CarteChiffre titre="Place libre">
        <Squelettes libelle="Chargement de la place libre" lignes={2} />
      </CarteChiffre>
    );
  }
  const libre = espace.total_o > 0 ? Math.min(1, espace.libre_o / espace.total_o) : 0;
  const repere = espace.total_o > 0 ? Math.min(1, seuilO / espace.total_o) : 0;
  return (
    <CarteChiffre titre="Place libre">
      <p className="font-mono text-2xl tabular-nums">{formaterOctets(espace.libre_o)}</p>
      <div
        className="relative h-2 rounded-full bg-muted"
        role="meter"
        aria-label="Place libre du volume"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(libre * 100)}
        aria-valuetext={`${formaterOctets(espace.libre_o)} libres sur ${formaterOctets(espace.total_o)}, seuil ${formaterOctets(seuilO)}`}
      >
        <div
          className={cn("h-full rounded-full", espace.libre_o < seuilO ? "bg-destructive" : "bg-success")}
          style={{ width: `${libre * 100}%` }}
        />
        <div
          className="absolute -inset-y-1 w-0.5 rounded-full bg-foreground"
          style={{ left: `${repere * 100}%` }}
          title={`Seuil : ${formaterOctets(seuilO)}`}
        />
      </div>
      <dl className="grid grid-cols-3 gap-2 text-13">
        <Valeur terme="Total">{formaterOctets(espace.total_o)}</Valeur>
        <Valeur terme="Libre">{formaterOctets(espace.libre_o)}</Valeur>
        <Valeur terme="Utilisé">{formaterOctets(espace.utilise_o)}</Valeur>
      </dl>
    </CarteChiffre>
  );
}

function CarteDebit({ debits }: Readonly<{ debits: DebitsEcriture | null }>) {
  return (
    <CarteChiffre titre="Débit d’écriture">
      {debits === null ? (
        <Squelettes libelle="Chargement du débit" lignes={2} />
      ) : (
        <>
          <p className="font-mono text-2xl tabular-nums">{formaterDebit(debits.debit_enregistrement_o_s)}</p>
          <dl className="grid gap-2 text-13">
            <Valeur terme="Débit (enregistrement en cours)">{formaterDebit(debits.debit_enregistrement_o_s)}</Valeur>
            <Valeur terme="Projection (toutes Caméras actives)">{formaterDebit(debits.debit_projection_o_s)}</Valeur>
          </dl>
        </>
      )}
    </CarteChiffre>
  );
}

function CarteConservation({ heures, debits }: Readonly<{ heures: number | null; debits: DebitsEcriture | null }>) {
  return (
    <CarteChiffre titre="Conservation">
      {heures === null || debits === null ? (
        <Squelettes libelle="Chargement de la Conservation" lignes={2} />
      ) : (
        <>
          <p className="font-mono text-2xl tabular-nums">{formaterConservation(heures)}</p>
          <dl className="grid gap-2 text-13">
            <Valeur terme="Enregistrement en cours">
              <Tenue secondes={debits.tenue_enregistrement_s} ok={debits.tenue_enregistrement_ok} />
            </Valeur>
            <Valeur terme="Toutes Caméras actives">
              <Tenue secondes={debits.tenue_projection_s} ok={debits.tenue_projection_ok} />
            </Valeur>
          </dl>
        </>
      )}
    </CarteChiffre>
  );
}

/** Tenue du disque face à la Conservation ; avertit (icône + texte) quand il ne suit pas. */
function Tenue({ secondes, ok }: Readonly<{ secondes: number | null; ok: boolean | null }>) {
  return (
    <span
      className={cn(
        "flex items-start gap-1.5",
        ok === false && "text-destructive",
        ok === null && "text-muted-foreground",
      )}
    >
      {ok === false && <TriangleAlert className="mt-0.5 size-3.5 shrink-0" role="img" aria-label="Avertissement" />}
      <span>
        Tenue estimée : {secondes === null ? libelleTenue(ok) : `${formaterDuree(secondes)} — ${libelleTenue(ok)}`}
      </span>
    </span>
  );
}

function Valeur({ terme, children }: Readonly<{ terme: string; children: ReactNode }>) {
  return (
    <div className="grid gap-0.5">
      <dt className="text-muted-foreground">{terme}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function Squelettes({ libelle, lignes }: Readonly<{ libelle: string; lignes: number }>) {
  return (
    <div className="space-y-2" aria-busy="true" aria-label={libelle}>
      {Array.from({ length: lignes }, (_, rang) => (
        <Skeleton key={rang} className={cn("w-full", rang === 0 ? "h-8" : "h-5")} />
      ))}
    </div>
  );
}

/** État vide : rien n'enregistre tant qu'aucune Caméra n'est configurée. */
function AucuneCamera() {
  return (
    <section
      aria-label="Aucune Caméra"
      className="flex flex-col items-center gap-3 rounded-lg border border-dashed bg-card px-6 py-12 text-center"
    >
      <HardDrive className="size-8 text-muted-foreground" aria-hidden="true" />
      <p className="text-base font-semibold">Aucune Caméra</p>
      <p className="text-muted-foreground">Ajoutez une Caméra, puis allumez son enregistrement dans ses Réglages.</p>
      <Button asChild variant="outline">
        <Link to="/administration/cameras">Aller aux Caméras</Link>
      </Button>
    </section>
  );
}

function LigneCamera({ camera }: Readonly<{ camera: DebitCamera }>) {
  const naviguer = useNavigate();
  const relire = () => void naviguer(`/relecture/${camera.id}`);
  return (
    <TableRow
      className="cursor-pointer"
      title={`Relire ${camera.nom}`}
      tabIndex={0}
      onClick={relire}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          relire();
        }
      }}
    >
      <TableCell className="font-medium">{camera.nom}</TableCell>
      <TableCell>
        <span className="flex items-center gap-1.5 text-13">
          <span
            className={cn("size-2 shrink-0 rounded-full", COULEURS_ETAT[camera.etat_enregistrement])}
            aria-hidden="true"
          />
          {libelleEtatEnregistrement(camera.etat_enregistrement)}
        </span>
      </TableCell>
      <TableCell className="font-mono text-xs">
        {formaterDebit(camera.debit_o_s)}
        {camera.source_debit !== "inconnu" && (
          <span className="text-muted-foreground"> ({libelleSourceDebit(camera.source_debit)})</span>
        )}
      </TableCell>
      <TableCell className="font-mono text-xs">
        {camera.plus_ancien_segment === null
          ? "aucun"
          : new Date(camera.plus_ancien_segment).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}
      </TableCell>
    </TableRow>
  );
}
