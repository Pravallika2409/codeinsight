import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

const linkClass = ({ isActive }) =>
  `px-3 py-1.5 text-sm rounded ${
    isActive ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
  }`;

export default function Navbar() {
  const { isAuthenticated, user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/");
  }

  return (
    <nav className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
      <NavLink to="/" className="font-bold text-slate-100">
        CodeInsight AI
      </NavLink>
      <div className="flex items-center gap-1">
        <NavLink to="/" end className={linkClass}>
          Home
        </NavLink>
        <NavLink to="/analyzer" className={linkClass}>
          Analyzer
        </NavLink>
        {isAuthenticated ? (
          <>
            <NavLink to="/projects" className={linkClass}>
              Projects
            </NavLink>
            <NavLink to="/history" className={linkClass}>
              History
            </NavLink>
            <span className="ml-2 text-xs text-slate-500">{user?.email}</span>
            <button onClick={handleLogout} className="px-3 py-1.5 text-sm text-slate-400 hover:text-slate-200">
              Log out
            </button>
          </>
        ) : (
          <>
            <NavLink to="/login" className={linkClass}>
              Log in
            </NavLink>
            <NavLink to="/register" className={linkClass}>
              Register
            </NavLink>
          </>
        )}
      </div>
    </nav>
  );
}
