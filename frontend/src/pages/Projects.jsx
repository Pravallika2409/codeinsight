import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { listProjects, createProject, deleteProject, ApiError } from "../services/api.js";
import GitHubImportPanel from "../components/GitHubImportPanel.jsx";

export default function Projects() {
  const [projects, setProjects] = useState(null);
  const [error, setError] = useState(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  const refresh = useCallback(() => {
    listProjects()
      .then(setProjects)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load projects."));
  }, []);

  useEffect(refresh, [refresh]);

  async function handleCreate(e) {
    e.preventDefault();
    setIsCreating(true);
    setError(null);
    try {
      await createProject({ name, description: description || undefined });
      setName("");
      setDescription("");
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create project.");
    } finally {
      setIsCreating(false);
    }
  }

  async function handleDelete(id) {
    try {
      await deleteProject(id);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete project.");
    }
  }

  return (
    <div className="mx-auto w-full max-w-2xl flex-1 p-4">
      <h1 className="mb-4 text-2xl font-bold text-slate-100">Projects</h1>

      <form onSubmit={handleCreate} className="mb-6 flex flex-col gap-2 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <div className="flex gap-2">
          <input
            placeholder="Project name"
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="flex-1 rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
          />
          <button
            type="submit"
            disabled={isCreating}
            className="rounded bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            New project
          </button>
        </div>
        <input
          placeholder="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="rounded border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
        />
      </form>

      {error && <p className="mb-3 text-sm text-severity-critical">{error}</p>}

      {projects === null ? (
        <p className="text-sm text-slate-500">Loading…</p>
      ) : projects.length === 0 ? (
        <p className="text-sm text-slate-500">No projects yet — create one above.</p>
      ) : (
        <ul className="space-y-2">
          {projects.map((p) => (
            <li key={p.id} className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium text-slate-100">{p.name}</p>
                  {p.description && <p className="text-sm text-slate-500">{p.description}</p>}
                  <p className="text-xs text-slate-600">{p.file_count} file{p.file_count === 1 ? "" : "s"}</p>
                </div>
                <div className="flex gap-3 text-sm">
                  <Link to={`/history?project_id=${p.id}`} className="text-indigo-400 hover:underline">
                    History
                  </Link>
                  <Link to={`/projects/${p.id}/analytics`} className="text-indigo-400 hover:underline">
                    Analytics
                  </Link>
                  <button onClick={() => handleDelete(p.id)} className="text-severity-critical hover:underline">
                    Delete
                  </button>
                </div>
              </div>
              <GitHubImportPanel projectId={p.id} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
