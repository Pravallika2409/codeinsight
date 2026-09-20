import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { login as loginRequest, ApiError } from "../services/api.js";
import { useAuth } from "../context/AuthContext.jsx";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  async function handleSubmit(e) {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      const { access_token } = await loginRequest({ email, password });
      login(access_token);
      navigate("/projects");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-4 px-4">
      <h1 className="text-2xl font-bold text-slate-100">Log in</h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <input
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100"
        />
        <input
          type="password"
          required
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100"
        />
        {error && <p className="text-sm text-severity-critical">{error}</p>}
        <button
          type="submit"
          disabled={isSubmitting}
          className="rounded-lg bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          {isSubmitting ? "Logging in…" : "Log in"}
        </button>
      </form>
      <p className="text-sm text-slate-500">
        No account?{" "}
        <Link to="/register" className="text-indigo-400 hover:underline">
          Register
        </Link>
      </p>
    </div>
  );
}
