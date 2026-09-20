import { Routes, Route } from "react-router-dom";
import Navbar from "./components/Navbar.jsx";
import RequireAuth from "./components/RequireAuth.jsx";
import Landing from "./pages/Landing.jsx";
import CodeAnalyzer from "./pages/CodeAnalyzer.jsx";
import Login from "./pages/Login.jsx";
import Register from "./pages/Register.jsx";
import Projects from "./pages/Projects.jsx";
import History from "./pages/History.jsx";
import Analytics from "./pages/Analytics.jsx";

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/analyzer" element={<CodeAnalyzer />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route
          path="/projects"
          element={
            <RequireAuth>
              <Projects />
            </RequireAuth>
          }
        />
        <Route
          path="/history"
          element={
            <RequireAuth>
              <History />
            </RequireAuth>
          }
        />
        <Route
          path="/projects/:projectId/analytics"
          element={
            <RequireAuth>
              <Analytics />
            </RequireAuth>
          }
        />
      </Routes>
    </div>
  );
}
