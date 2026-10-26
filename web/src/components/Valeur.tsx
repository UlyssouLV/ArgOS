import type { ReactNode } from "react";

/** Paire terme / valeur d'une liste de définitions (`<dl>`) d'une carte. */
export function Valeur({ terme, children }: Readonly<{ terme: string; children: ReactNode }>) {
  return (
    <div className="grid gap-1">
      <dt className="text-13 text-muted-foreground">{terme}</dt>
      <dd>{children}</dd>
    </div>
  );
}
