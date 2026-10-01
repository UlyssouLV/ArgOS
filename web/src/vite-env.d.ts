/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Port de l'API du Site, sur le même hôte que la page (défaut 8000). */
  readonly VITE_ARGOS_PORT_API?: string;
}
