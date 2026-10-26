import type { ReactNode } from "react";

/** Page pas encore redessinée en 1.0.0 : garde l'ancienne feuille (styles.css) sous la coquille. */
export function AncienStyle({ children }: Readonly<{ children: ReactNode }>) {
  return <div className="ancien-style">{children}</div>;
}
