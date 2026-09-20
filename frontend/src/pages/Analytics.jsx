import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { getProjectAnalytics, ApiError } from "../services/api.js";

function ScoreTrendBars({ trend }) {
  if (trend.length === 0) return null;
  return (
    <div className="flex h-24 items-end gap-1">
      {trend.map((point) => (
        <div
          key={point.analysis_id}
          title={`${point.filename}: ${point.score_total}/100`}
          className="flex-1 rounded-t bg-indigo-500/70"
          style={{ height: `${Math.max(4, point.score_total)}%` }}
        />
      ))}
    </div>
  );
}

export default function Analytics() {
  const { projectId } = useParams();
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getProjectAnalytics(Number(projectId))
      .then(setAnalytics)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load analytics."));
  }, [projectId]);

  if (error) {
    return <p className="p-6 text-sm text-severity-critical">{error}</p>;
  }
  if (!analytics) {
    return <p className="p-6 text-sm text-slate-500">Loading…</p>;
  }

  return (
    <div className="mx-auto w-full max-w-2xl flex-1 space-y-4 p-4">
      <Link to="/projects" className="text-sm text-indigo-400 hover:underline">
        ← Projects
      </Link>
      <h1 className="text-2xl font-bold text-slate-100">Project analytics</h1>

      {analytics.total_runs === 0 ? (
        <p className="text-sm text-slate-500">No analyses saved to this project yet.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <div className="rounded border border-slate-800 bg-slate-900/60 p-3 text-center">
              <div className="text-2xl font-bold text-slate-100">{analytics.total_runs}</div>
              <div className="text-xs uppercase text-slate-500">Analyses</div>
            </div>
            <div className="rounded border border-slate-800 bg-slate-900/60 p-3 text-center">
              <div className="text-2xl font-bold text-slate-100">{analytics.average_score}</div>
              <div className="text-xs uppercase text-slate-500">Avg score</div>
            </div>
            <div className="rounded border border-slate-800 bg-slate-900/60 p-3 text-center">
              <div className="text-2xl font-bold text-severity-critical">
                {(analytics.severity_totals.critical || 0) + (analytics.severity_totals.high || 0)}
              </div>
              <div className="text-xs uppercase text-slate-500">Critical+High</div>
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="mb-2 text-sm font-semibold uppercase text-slate-500">Score trend</h2>
            <ScoreTrendBars trend={analytics.score_trend} />
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
            <h2 className="mb-2 text-sm font-semibold uppercase text-slate-500">Languages analyzed</h2>
            <ul className="text-sm text-slate-300">
              {Object.entries(analytics.language_breakdown).map(([lang, count]) => (
                <li key={lang} className="flex justify-between">
                  <span>{lang}</span>
                  <span>{count}</span>
                </li>
              ))}
            </ul>
          </div>

          {analytics.top_rule_ids.length > 0 && (
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
              <h2 className="mb-2 text-sm font-semibold uppercase text-slate-500">Most frequent findings</h2>
              <ul className="text-sm text-slate-300">
                {analytics.top_rule_ids.map((rf) => (
                  <li key={rf.rule_id} className="flex justify-between">
                    <span>{rf.rule_id}</span>
                    <span className="text-slate-500">{rf.count}×</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {analytics.worst_files.length > 0 && (
            <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
              <h2 className="mb-2 text-sm font-semibold uppercase text-slate-500">Lowest-scoring files</h2>
              <ul className="text-sm text-slate-300">
                {analytics.worst_files.map((f) => (
                  <li key={f.analysis_id} className="flex justify-between">
                    <span>{f.filename}</span>
                    <span className="text-slate-500">{f.score_total}/100</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
