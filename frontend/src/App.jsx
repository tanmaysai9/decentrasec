import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import SatelliteShares from "./pages/SatelliteShares";

function App() {
  const token = sessionStorage.getItem("sds_token");
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={token ? <Navigate to="/dashboard" /> : <Login />} />
        <Route path="/dashboard" element={token ? <Dashboard /> : <Navigate to="/" />} />
        <Route path="/satellite" element={<SatelliteShares />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
