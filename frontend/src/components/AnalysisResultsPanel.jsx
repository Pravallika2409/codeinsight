import { useState, useMemo } from "react";
import FindingCard from "./FindingCard.jsx";
import ScorePanel from "./ScorePanel.jsx";
import SeverityBar from "./SeverityBar.jsx";
import CategoryFilter from "./CategoryFilter.jsx";
import AIReviewPanel from "./AIReviewPanel.jsx";

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];

export default function AnalysisResultsPanel({ result }) {
  const [activeCategory, setActiveCategory] = useState("all");

  const sortedFindings = useMemo(
    () =>
      [...result.findings].sort(
        (a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity)
      ),
    [result]
  );

  const availableCategories = useMemo(
    () => [...new Set(sortedFindings.map((f) => f.category))],
    [sortedFindings]
  );

  const visibleFindings = useMemo(
    () =>
      activeCategory === "all"
        ? sortedFindings
        : sortedFindings.filter((f) => f.category === activeCategory),
    [sortedFindings, activeCategory]
  );

  return (
    <>
      <ScorePanel score={result.score} summary={result.summary} />

      <AIReviewPanel aiReview={result.ai_review} />

      <SeverityBar
        counts={{
          critical: result.critical_count,
          high: result.high_count,
          medium: result.medium_count,
          low: result.low_count,
          info: result.info_count,
        }}
      />

      <div className="grid grid-cols-2 gap-2 text-center text-sm sm:grid-cols-5">
        {SEVERITY_ORDER.map((sev) => (
          <div key={sev} className="rounded border border-slate-800 bg-slate-900/60 py-2">
            <div className="text-lg font-bold text-slate-100">{result[`${sev}_count`]}</div>
            <div className="text-xs uppercase text-slate-500">{sev}</div>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3 text-sm text-slate-300">
        <span className="font-medium text-slate-200">Complexity: </span>
        time {result.complexity.time_complexity ?? "n/a"}, space{" "}
        {result.complexity.space_complexity ?? "n/a"}
        {result.complexity.is_estimated && <span className="ml-1 text-slate-500">(estimated)</span>}
      </div>

      <CategoryFilter categories={availableCategories} active={activeCategory} onChange={setActiveCategory} />

      <div className="flex-1 space-y-3 overflow-y-auto">
        {visibleFindings.length === 0 ? (
          <p className="text-sm text-slate-500">
            {sortedFindings.length === 0 ? "No issues detected." : "No issues in this category."}
          </p>
        ) : (
          visibleFindings.map((finding, i) => <FindingCard key={`${finding.rule_id}-${i}`} finding={finding} />)
        )}
      </div>
    </>
  );
}
