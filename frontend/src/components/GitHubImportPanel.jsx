import { useState, useRef, useEffect } from "react";
import { analyzeGithubRepo, getGithubAnalysisStatus, ApiError } from "../services/api.js";

const POLL_INTERVAL_MS = 2000;

export default function GitHubImportPanel({ projectId }) {
  const [isOpen, setIsOpen] = useState(false);
  const [repoUrl, setRepoUrl] = useState("");
  const [taskId, setTaskId] = useState(null);
  const [status, setStatus] = useState(null); // "pending" | "started" | "success" | "failure"
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => () => clearInterval(pollRef.current), []);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setReport(null);
    try {
      const { task_id } = await analyzeGithubRepo({ repo_url: repoUrl, project_id: projectId });
      setTaskId(task_id);
      setStatus("pending");
      pollRef.current = setInterval(async () => {
        const result = await getGithubAnalysisStatus(task_id);
        setStatus(result.status);
        if (result.status === "success" || result.status === "failure") {
          clearInterval(pollRef.current);
          if (result.status === "success") setReport(result.result);
          else setError(result.error || "Repository analysis failed.");
        }
      }, POLL_INTERVAL_MS);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start repository analysis.");
    }
  }

  if (!isOpen) {
    return (
      <button onClick={() => setIsOpen(true)} className="text-indigo-400 hover:underline">
        Import from GitHub
      </button>
    );
  }

  return (
    <div className="mt-2 rounded border border-slate-800 bg-slate-950 p-3">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          placeholder="owner/repo or https://github.com/owner/repo"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          required
          disabled={status === "pending" || status === "started"}
          className="flex-1 rounded border border-slate-700 bg-slate-900 px-2 py-1 text-sm text-slate-100"
        />
        <button
          type="submit"
          disabled={status === "pending" || status === "started"}
          className="rounded bg-indigo-600 px-3 py-1 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          Analyze
        </button>
      </form>

      {(status === "pending" || status === "started") && (
        <p className="mt-2 text-xs text-slate-500">Fetching and analyzing repository files…</p>
      )}
      {error && <p className="mt-2 text-xs text-severity-critical">{error}</p>}
      {report && (
        <div className="mt-2 text-xs text-slate-300">
          <p>
            <span className="font-medium text-slate-200">{report.repo}</span> — analyzed{" "}
            {report.files_analyzed} file{report.files_analyzed === 1 ? "" : "s"}
            {report.files_skipped > 0 && ` (${report.files_skipped} skipped)`}, average score{" "}
            <span className="font-medium text-slate-200">{report.average_score}/100</span>
          </p>
          <p className="mt-1 text-slate-500">
            {report.critical_count} critical, {report.high_count} high across all analyzed files.
          </p>
        </div>
      )}
    </div>
  );
}
