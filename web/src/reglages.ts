import { appeler } from "./api";
import { Refus } from "./cameras";

export type Coin = "UpperLeft" | "UpperRight" | "LowerLeft" | "LowerRight";
/** Position d'une Incrustation ; `Custom` : hors d'un coin, placée par la caméra. */
export type Position = Coin | "Custom";
export const COINS: Coin[] = ["UpperLeft", "UpperRight", "LowerLeft", "LowerRight"];

export type Horloge = {
  date_heure_utc: string;
  /** Écart avec l'heure du Site, en secondes ; positif : la caméra avance. */
  ecart_s: number;
  fuseau_posix: string | null;
  /** Nom IANA (`Europe/Paris`) si ArgOS reconnaît le fuseau POSIX. */
  fuseau: string | null;
  mode: "manuel" | "ntp";
  serveur_ntp: string | null;
};

export type IncrustationNom = {
  affichee: boolean;
  texte: string | null;
  position: Position | null;
  peut_etre_reaffichee: boolean;
};

export type IncrustationDateHeure = {
  affichee: boolean;
  format: string | null;
  position: Position | null;
  peut_etre_reaffichee: boolean;
};

/** `IrCutFilter` ONVIF : `ON` = filtre posé (jour), `OFF` = filtre retiré (nuit), `AUTO` = automatique. */
export type ModeInfrarouge = "ON" | "OFF" | "AUTO";
export type ModeCompensation = "OFF" | "ON";
export type Bornes = { min: number; max: number };

/** Paramètres d'image bornés : réglés par un curseur. */
export type ParametreImage = "luminosite" | "contraste" | "saturation" | "nettete";
export const PARAMETRES_IMAGE: ParametreImage[] = ["luminosite", "contraste", "saturation", "nettete"];
/** Compensations à mode (coupé, activé) et, quand la caméra le borne, niveau. */
export type CompensationImage = "contre_jour" | "wdr";
export const COMPENSATIONS_IMAGE: CompensationImage[] = ["contre_jour", "wdr"];

/** Image relue ; `null` : paramètre que la caméra ne propose pas. */
export type ValeursImage = {
  infrarouge: ModeInfrarouge | null;
  luminosite: number | null;
  contraste: number | null;
  saturation: number | null;
  nettete: number | null;
  contre_jour: ModeCompensation | null;
  contre_jour_niveau: number | null;
  wdr: ModeCompensation | null;
  wdr_niveau: number | null;
};
export type ChampImage = keyof ValeursImage;

/** Ce que la caméra propose : modes, ou bornes ; `null` : non proposé. */
export type OptionsImage = {
  infrarouge: ModeInfrarouge[] | null;
  luminosite: Bornes | null;
  contraste: Bornes | null;
  saturation: Bornes | null;
  nettete: Bornes | null;
  contre_jour: ModeCompensation[] | null;
  contre_jour_niveau: Bornes | null;
  wdr: ModeCompensation[] | null;
  wdr_niveau: Bornes | null;
};

/** Image de l'Appareil (première source vidéo), partagée par toutes ses Caméras. */
export type Image = {
  reglable: boolean;
  /** `non_reglable` : pas de service image, ou il répond en faute. */
  raison: "non_reglable" | null;
  valeurs: ValeursImage | null;
  options: OptionsImage | null;
};

/** Encodage relu ; `resolution` : `largeur`x`hauteur` ; `null` : valeur que la caméra ne donne pas. */
export type ValeursEncodage = {
  resolution: string;
  images_par_seconde: number | null;
  /** kbit/s. */
  debit_max: number | null;
  codec: string;
  qualite: number | null;
  intervalle_images_cles: number | null;
};

/** Ce que la caméra propose ; `null` : non proposé. */
export type OptionsEncodage = {
  resolutions: string[];
  images_par_seconde: Bornes | null;
  debit_max: Bornes | null;
};

/**
 * Encodage du Flux de la Caméra (profil de son URL RTSP), docs/adr/0008-encodage-par-media-2-media-1-seulement-en-h264.md.
 * `profil_introuvable` : aucun profil à l'URL RTSP ; `non_reglable` : ni média 2, ni Flux en H.264 (valeurs en
 * lecture seule).
 */
export type Encodage = {
  reglable: boolean;
  raison: "profil_introuvable" | "non_reglable" | null;
  profil: string | null;
  valeurs: ValeursEncodage | null;
  options: OptionsEncodage | null;
};

/** Champs d'Encodage réglables. */
export type ChampEncodage = "resolution" | "images_par_seconde" | "debit_max";

/** Réglages de la Caméra, lus sur la caméra par ONVIF à chaque ouverture. */
export type Reglages = {
  horloge: Horloge;
  incrustations: { nom: IncrustationNom; date_heure: IncrustationDateHeure };
  image: Image;
  encodage: Encodage;
};

/** Sécurité de l'échange ONVIF avec la caméra (docs/adr/0007-onvif-en-https-par-cle-memorisee.md). */
export type SecuriteOnvif = {
  chiffre: boolean;
  /** Empreinte SHA-256 (hexadécimal) de la clé publique du Certificat de l'Appareil ; `null` hors HTTPS. */
  empreinte: string | null;
  empreinte_memorisee_le: string | null;
  /** TLS 1.0 ou 1.1 : accepté, mais signalé. */
  tls_ancien: boolean;
  /** ONVIF en clair avec un mot de passe court : seulement « court » ou non, jamais le mot de passe. */
  mot_de_passe_court: boolean;
};

/** Réglages lus à l'ouverture, avec la sécurité de l'échange. */
export type ReglagesLus = Reglages & { securite: SecuriteOnvif };

/** Empreinte du Certificat de l'Appareil par groupes de 4 chiffres, pour la comparer à l'œil. */
export function empreinteGroupee(empreinte: string): string {
  return (empreinte.match(/.{1,4}/g) ?? []).join(" ");
}

/** Empreinte courte du Certificat de l'Appareil : ses 16 premiers chiffres, par groupes de 4. */
export function empreinteCourte(empreinte: string): string {
  return empreinteGroupee(empreinte.slice(0, 16));
}

/** Clé mémorisée (et sa date) et clé que la caméra présente, renvoyées avec `certificat_change`. */
export type CertificatsCompares = {
  empreinte_memorisee: string | null;
  empreinte_memorisee_le: string | null;
  empreinte_presentee: string | null;
};

export type CodeOnvif =
  | "sans_onvif"
  | "identifiants_refuses"
  | "injoignable"
  | "certificat_change"
  | "https_indisponible"
  | "en_clair_non_accepte";

/** `502` des Réglages : `code` dit lequel ; `certificat_change` porte les deux empreintes. */
export class RefusOnvif extends Refus {
  constructor(
    message: string,
    readonly code: CodeOnvif,
    readonly certificat: CertificatsCompares | null,
  ) {
    super(message);
  }
}

/** « Faire confiance au nouveau certificat » : l'API refuse si la caméra ne présente plus cette empreinte. */
export async function faireConfiance(idCamera: number, empreinte: string): Promise<void> {
  const reponse = await appeler(`/api/cameras/${idCamera}/reglages/certificat`, {
    method: "POST",
    body: JSON.stringify({ empreinte }),
  });
  if (!reponse.ok) return lever(reponse);
}

/** « Oublier le certificat de cette caméra » : le contact suivant repart de zéro. */
export async function oublierCertificat(idCamera: number): Promise<void> {
  const reponse = await appeler(`/api/cameras/${idCamera}/reglages/certificat`, { method: "DELETE" });
  if (!reponse.ok) return lever(reponse);
}

/** « Régler quand même en clair » (`accepte`), ou retrait de l'accord ONVIF en clair. */
export async function accepterEnClair(idCamera: number, accepte: boolean): Promise<void> {
  const reponse = await appeler(`/api/cameras/${idCamera}/reglages/onvif-en-clair`, {
    method: accepte ? "PUT" : "DELETE",
  });
  if (!reponse.ok) return lever(reponse);
}

export async function lireReglages(idCamera: number): Promise<ReglagesLus> {
  const reponse = await appeler(`/api/cameras/${idCamera}/reglages`);
  if (reponse.ok) return reponse.json();
  return lever(reponse);
}

/** Envoie une fois l'heure du Site à la caméra (mode manuel, fuseau gardé) ; rend son Horloge relue. */
export async function mettreALHeure(idCamera: number): Promise<Horloge> {
  const reponse = await appeler(`/api/cameras/${idCamera}/reglages/mise-a-l-heure`, { method: "POST" });
  if (reponse.ok) return reponse.json();
  return lever(reponse);
}

/** Envoie seulement les champs modifiés ; l'API relit la caméra et dit, pour chacun, s'il a été pris. */
export async function modifierReglages(idCamera: number, modification: Modification): Promise<ResultatModification> {
  const reponse = await appeler(`/api/cameras/${idCamera}/reglages`, {
    method: "PATCH",
    body: JSON.stringify(modification),
  });
  if (reponse.ok) return reponse.json();
  return lever(reponse);
}

/** `detail` de l'API affiché tel quel ; un `502` (refus ONVIF) garde aussi son code et ses empreintes. */
async function lever(reponse: Response): Promise<never> {
  const corps = (await reponse.json().catch(() => ({}))) as {
    detail?: unknown;
    code?: CodeOnvif;
    certificat?: CertificatsCompares | null;
  };
  const message = typeof corps.detail === "string" ? corps.detail : `Refusé par l'API (${reponse.status}).`;
  if (reponse.status === 502 && corps.code) throw new RefusOnvif(message, corps.code, corps.certificat ?? null);
  throw new Refus(message);
}

const POSITIONS: Record<Position, string> = {
  UpperLeft: "en haut à gauche",
  UpperRight: "en haut à droite",
  LowerLeft: "en bas à gauche",
  LowerRight: "en bas à droite",
  Custom: "position personnalisée",
};

export function textePosition(position: Position | null): string {
  return position === null ? "—" : POSITIONS[position];
}

export const INFRAROUGE: Record<ModeInfrarouge, string> = { ON: "jour", OFF: "nuit", AUTO: "automatique" };
export const COMPENSATION: Record<ModeCompensation, string> = { OFF: "coupé", ON: "activé" };

/** Résolution lisible : `1920x1080` → `1920×1080`. */
export function texteResolution(resolution: string): string {
  return resolution.replace("x", "×");
}

/** Pas d'un curseur : au centième sur une plage étroite (0 à 1…), à l'unité sinon. */
export function pasDe(bornes: Bornes): number {
  return bornes.max - bornes.min <= 10 ? 0.01 : 1;
}

const UNITES: [number, string, string][] = [
  [365.25 * 24 * 3600, "an", "ans"],
  [24 * 3600, "jour", "jours"],
  [3600, "h", "h"],
  [60, "min", "min"],
  [1, "s", "s"],
];

/** « en retard de 26 ans », « en avance de 3 min » ; « à l'heure » à moins d'une seconde près. */
export function texteEcart(ecartS: number): string {
  const absolu = Math.abs(ecartS);
  const unite = UNITES.find(([duree]) => absolu >= duree);
  if (!unite) return "à l'heure";
  const [duree, singulier, pluriel] = unite;
  const nombre = Math.floor(absolu / duree);
  return `${ecartS < 0 ? "en retard" : "en avance"} de ${nombre} ${nombre > 1 ? pluriel : singulier}`;
}

/** Fuseaux proposés, Europe/Paris en tête : ceux que l'API sait relire sous le même nom. */
export async function lireFuseaux(): Promise<string[]> {
  const reponse = await appeler("/api/fuseaux");
  if (reponse.ok) return reponse.json();
  return lever(reponse);
}

/** Fuseau lisible s'il est reconnu, sinon la chaîne POSIX de la caméra telle quelle ; `""` : sans fuseau. */
export function fuseauLu(horloge: Horloge): string {
  return horloge.fuseau ?? horloge.fuseau_posix ?? "";
}

/** Date et heure UTC de la caméra, au format français. */
export function texteDateHeure(dateHeureUtc: string): string {
  return new Date(dateHeureUtc).toLocaleString("fr-FR", { timeZone: "UTC" });
}

export type CleIncrustation = "nom" | "date_heure";

/** Champs modifiés d'une Incrustation : seuls ceux présents sont envoyés à la caméra. */
export type ModificationIncrustation = { affichee?: boolean; texte?: string; position?: Coin };

/** Champs d'Image modifiés : seuls ceux présents sont envoyés à la caméra. */
export type ModificationImage = Partial<{ [C in ChampImage]: NonNullable<ValeursImage[C]> }>;

/** Champs d'Encodage modifiés : seuls ceux présents sont envoyés à la caméra. */
export type ModificationEncodage = Partial<SaisieEncodage>;

/** `horloge` absent : fuseau inchangé ; `image` absente : Image inchangée ; `encodage` absent : Flux non coupé. */
export type Modification = {
  horloge?: { fuseau: string };
  incrustations: Partial<Record<CleIncrustation, ModificationIncrustation>>;
  image?: ModificationImage;
  encodage?: ModificationEncodage;
};

export type StatutChamp = "pris" | "pas_pris" | "refuse";

/**
 * Résultat d'un champ envoyé : `champ` vaut `horloge.fuseau`, `incrustations.nom.texte`, `image.luminosite`… ;
 * fuseau relu en POSIX.
 */
export type ChampModifie = {
  champ: string;
  demande: string | boolean | number;
  relu: string | boolean | number | null;
  statut: StatutChamp;
  /** `sans_reponse` : la caméra n'a plus répondu après l'envoi d'Encodage. */
  raison?: "sans_reponse" | null;
};

export type ResultatModification = { champs: ChampModifie[]; reglages: Reglages };

/** Valeurs du formulaire d'une Incrustation ; `texte` ne sert qu'au nom. */
export type IncrustationSaisie = { affichee: boolean; texte: string; position: Position };

/** Encodage saisi ; un nombre effacé vaut `NaN`, hors des bornes. */
export type SaisieEncodage = { resolution: string; images_par_seconde: number; debit_max: number };

/**
 * `fuseau` : nom IANA, ou fuseau inconnu de la caméra tel quel tant qu'il n'est pas changé.
 * `image` : `null` si l'Image n'est pas réglable ; `encodage` : `null` si l'Encodage ne l'est pas.
 */
export type Saisie = {
  fuseau: string;
  incrustations: Record<CleIncrustation, IncrustationSaisie>;
  image: ValeursImage | null;
  encodage: SaisieEncodage | null;
};

// Coin proposé pour une Incrustation cachée qu'on réaffiche : celui de la caméra « sortie d'usine ».
const COINS_PAR_DEFAUT: Record<CleIncrustation, Coin> = { nom: "UpperLeft", date_heure: "LowerLeft" };

export function saisieDepuis(reglages: Reglages): Saisie {
  const { nom, date_heure } = reglages.incrustations;
  return {
    fuseau: fuseauLu(reglages.horloge),
    incrustations: {
      nom: { affichee: nom.affichee, texte: nom.texte ?? "", position: nom.position ?? COINS_PAR_DEFAUT.nom },
      date_heure: {
        affichee: date_heure.affichee,
        texte: "",
        position: date_heure.position ?? COINS_PAR_DEFAUT.date_heure,
      },
    },
    image: reglages.image.valeurs && { ...reglages.image.valeurs },
    encodage: saisieEncodage(reglages.encodage),
  };
}

function saisieEncodage(encodage: Encodage): SaisieEncodage | null {
  const valeurs = encodage.valeurs;
  if (!encodage.reglable || !valeurs) return null;
  return {
    resolution: valeurs.resolution,
    images_par_seconde: valeurs.images_par_seconde ?? Number.NaN,
    debit_max: valeurs.debit_max ?? Number.NaN,
  };
}

/** Champs d'Encodage saisis qui diffèrent de la caméra ; un champ que la caméra ne borne pas n'est jamais envoyé. */
function modificationEncodage(actuel: Encodage, saisie: SaisieEncodage | null): ModificationEncodage {
  const encodage: ModificationEncodage = {};
  const valeurs = actuel.valeurs;
  const options = actuel.options;
  if (!saisie || !valeurs || !options) return encodage;
  if (saisie.resolution !== valeurs.resolution) encodage.resolution = saisie.resolution;
  if (options.images_par_seconde && saisie.images_par_seconde !== valeurs.images_par_seconde) {
    encodage.images_par_seconde = saisie.images_par_seconde;
  }
  if (options.debit_max && saisie.debit_max !== valeurs.debit_max) encodage.debit_max = saisie.debit_max;
  return encodage;
}

/** Champs d'Encodage saisis hors des options de la caméra : rien ne part tant qu'il y en a. */
export function encodageHorsBornes(encodage: Encodage, saisie: SaisieEncodage | null): ChampEncodage[] {
  const options = encodage.options;
  if (!saisie || !options) return [];
  const dehors: ChampEncodage[] = [];
  if (!options.resolutions.includes(saisie.resolution)) dehors.push("resolution");
  for (const champ of ["images_par_seconde", "debit_max"] as const) {
    const bornes = options[champ];
    const valeur = saisie[champ];
    if (bornes && !(valeur >= bornes.min && valeur <= bornes.max)) dehors.push(champ);
  }
  return dehors;
}

/** Champs d'Image saisis qui diffèrent de la caméra ; un paramètre non proposé (`null`) n'est jamais envoyé. */
function modificationImage(actuelle: ValeursImage | null, saisie: ValeursImage | null): ModificationImage {
  const image: Record<string, unknown> = {};
  if (!actuelle || !saisie) return image;
  for (const champ of Object.keys(saisie) as ChampImage[]) {
    const valeur = saisie[champ];
    if (valeur !== null && valeur !== actuelle[champ]) image[champ] = valeur;
  }
  return image as ModificationImage;
}

/**
 * Champs de `saisie` qui diffèrent de la caméra (`actuels`) ; une Incrustation réaffichée part avec texte et coin.
 * Le fuseau n'est envoyé que changé pour un fuseau de la liste.
 */
export function modificationsEntre(actuels: Reglages, saisie: Saisie): Modification {
  const incrustations: Modification["incrustations"] = {};
  for (const cle of ["nom", "date_heure"] as const) {
    const lue = actuels.incrustations[cle];
    const saisi = saisie.incrustations[cle];
    const champs: ModificationIncrustation = {};
    if (!saisi.affichee) {
      if (lue.affichee) champs.affichee = false;
    } else {
      const reaffichee = !lue.affichee;
      if (reaffichee) champs.affichee = true;
      if (cle === "nom" && (reaffichee || saisi.texte !== (lue as IncrustationNom).texte)) champs.texte = saisi.texte;
      if (saisi.position !== "Custom" && (reaffichee || saisi.position !== lue.position)) {
        champs.position = saisi.position;
      }
    }
    if (Object.keys(champs).length > 0) incrustations[cle] = champs;
  }
  const modification: Modification = { incrustations };
  if (saisie.fuseau !== fuseauLu(actuels.horloge)) modification.horloge = { fuseau: saisie.fuseau };
  const image = modificationImage(actuels.image.valeurs, saisie.image);
  if (Object.keys(image).length > 0) modification.image = image;
  const encodage = modificationEncodage(actuels.encodage, saisie.encodage);
  if (Object.keys(encodage).length > 0) modification.encodage = encodage;
  return modification;
}

export function estVide(modification: Modification): boolean {
  return (
    !modification.horloge &&
    !modification.image &&
    !modification.encodage &&
    Object.keys(modification.incrustations).length === 0
  );
}
