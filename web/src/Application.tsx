import { BrowserRouter, Navigate, Route, Routes } from "react-router";

import { Administration } from "./pages/Administration";
import { Connexion } from "./pages/Connexion";
import { Enregistrement } from "./pages/Enregistrement";
import { HeureDuSite } from "./pages/HeureDuSite";
import { Live } from "./pages/Live";
import { Relecture } from "./pages/Relecture";
import { ZoneConnectee } from "./pages/ZoneConnectee";
import { FournisseurSession } from "./session";

export function Application() {
  return (
    <FournisseurSession>
      <BrowserRouter>
        <Routes>
          <Route path="/connexion" element={<Connexion />} />
          <Route element={<ZoneConnectee />}>
            <Route path="/live" element={<Live />} />
            <Route path="/enregistrement" element={<Enregistrement />} />
            <Route path="/relecture" element={<Relecture />} />
            <Route path="/relecture/:idCamera" element={<Relecture />} />
            <Route path="/administration/cameras" element={<Administration />} />
            <Route path="/administration/heure-du-site" element={<HeureDuSite />} />
          </Route>
          <Route path="/administration" element={<Navigate to="/administration/cameras" replace />} />
          <Route path="*" element={<Navigate to="/live" replace />} />
        </Routes>
      </BrowserRouter>
    </FournisseurSession>
  );
}
