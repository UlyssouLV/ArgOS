import { toast } from "sonner";

/** Résultat d'une action en toast (bas à droite, coquille), lisible dans un rôle `status`. */
export function notifier(message: string, issue: "succes" | "echec" = "succes") {
  const contenu = <span role="status">{message}</span>;
  if (issue === "succes") toast.success(contenu);
  else toast.error(contenu);
}
