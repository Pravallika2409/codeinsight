import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { getAnalysisHistory, getAnalysisDetail, ApiError } from "../services/api.js";
import AnalysisResultsPanel from "../components/AnalysisResultsPanel.jsx";

export default function History() {
  const [searchParams] = useSearchParams();
  const projectId = searchParams.get("project_id");

  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  const refresh = useCallback(() => {
    getAnalysisHistory(projectId ? Number(projectId) : undefined)
      .then(setItems)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load history."));
  }, [projectId]);

  useEffect(refresh, [refresh]);

  async function handleSelect(id) {
    setSelectedId(id);
    setIsLoadingDetail(true);
    setDetail(null);
    try {
      const data = await getAnalysisDetail(id);
      setDetail(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load analysis.");
    } finally {
      setIsLoadingDetail(false);
    }
  }

  return (
    <div className="grid flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-2">
      <section className="flex flex-col rounded-lg border border-slate-800 bg-slate-900/40 p-4">
        <h1 className="mb-3 text-xl font-bold text-slate-100">
          Analysis history {projectId && <span className="text-sm font-normal text-slate-500">(this project)</span>}
        </h1>

        {error && <p className="mb-3 text-sm text-severity-critical">{error}</p>}

        {items === null ? (
          <p className="text-sm text-slate-500">Loading…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-slate-500">No saved analyses yet.</p>
        ) : (
          <ul className="space-y-2 overflow-y-auto">
            {items.map((item) => (
              <li key={item.id}>
                <button
                  onClick={() => handleSelect(item.id)}
                  className={`flex w-full items-center justify-between rounded-lg border p-3 text-left transition ${
                    selectedId === item.id
                      ? "border-indigo-500 bg-indigo-600/10"
                      : "border-slate-800 bg-slate-900/60 hover:border-slate-700"
                  }`}
                >
                  <div>
                    <p className="font-medium text-slate-100">{item.filename}</p>
                    <p className="text-xs text-slate-500">
                      {item.language} · {new Date(item.created_at).toLocaleString()}
                    </p>
                  </div>
                  <div className="text-right text-sm">
                    <p className="font-bold text-slate-100">{item.score_total}/100</p>
                    {(item.critical_count > 0 || item.high_count > 0) && (
                      <p className="text-xs text-severity-high">
                        {item.critical_count} critical, {item.high_count} high
                      </p>
                    )}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-col gap-4">
        {isLoadingDetail && <p className="text-sm text-slate-500">Loading analysis…</p>}
        {!isLoadingDetail && !detail && (
          <p className="text-sm text-slate-500">Select an analysis on the left to view its full report.</p>
        )}
        {detail && <AnalysisResultsPanel result={detail} />}
      </section>
    </div>
  );
}
