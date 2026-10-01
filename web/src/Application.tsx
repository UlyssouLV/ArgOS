import { BrowserRouter, Navigate, Route, Routes } from "react-router";

import { Administration } from "./pages/Administration";
import { Connexion } from "./pages/Connexion";
import { Live } from "./pages/Live";
import { ZoneConnectee } from "./pages/ZoneConnectee";
import { FournisseurSession } from "./session";

export function Application() {
  return (
    <FournisseurSession>
      <BrowserRouter>
        <Routes>
          <Route path="/connexion" element={<Connexion />} />
          <Route element={<ZoneConnectee />}>
            <Route path="/administration" element={<Administration />} />
            <Route path="/live" element={<Live />} />
          </Route>
          <Route path="*" element={<Navigate to="/administration" replace />} />
        </Routes>
      </BrowserRouter>
    </FournisseurSession>
  );
}
