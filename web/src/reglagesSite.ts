import { appeler } from "./api";

export const CONSERVATION_MIN = 1;
export const CONSERVATION_MAX = 24;

export type ReglagesSite = {
  conservation_h: number;
};

export async function lireReglagesSite(): Promise<ReglagesSite> {
  const reponse = await appeler("/api/reglages-site");
  if (!reponse.ok) throw new Error(`Lecture des réglages Site : ${reponse.status}`);
  return reponse.json();
}

export async function modifierReglagesSite(conservation_h: number): Promise<ReglagesSite> {
  const reponse = await appeler("/api/reglages-site", {
    method: "PATCH",
    body: JSON.stringify({ conservation_h }),
  });
  if (!reponse.ok) throw new Error(`Mise à jour des réglages Site : ${reponse.status}`);
  return reponse.json();
}
