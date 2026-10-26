import { useEffect, type ReactNode } from "react";

/** Titre de l'onglet du navigateur pour une page : « <Page> · ArgOS ». */
export function useTitreOnglet(titre: string) {
  useEffect(() => {
    document.title = `${titre} · ArgOS`;
  }, [titre]);
}

/** En-tête collant d'une page de la zone connectée : surtitre, titre, actions de page à droite. */
export function EnTeteDePage({
  titre,
  surtitre,
  actions,
}: Readonly<{ titre: string; surtitre?: string; actions?: ReactNode }>) {
  useTitreOnglet(titre);
  return (
    <header className="sticky top-0 z-10 flex min-h-16 items-center gap-4 border-b bg-background/95 px-6 py-3 backdrop-blur">
      <div className="min-w-0 flex-1">
        {surtitre && <p className="text-xs font-medium text-muted-foreground uppercase">{surtitre}</p>}
        <h1 className="truncate text-xl font-semibold">{titre}</h1>
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </header>
  );
}
