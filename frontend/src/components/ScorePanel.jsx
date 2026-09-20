const PENALTY_ROWS = [
  { key: "bug_penalty", label: "Bugs" },
  { key: "security_penalty", label: "Security" },
  { key: "complexity_penalty", label: "Complexity" },
  { key: "maintainability_penalty", label: "Maintainability" },
];

function scoreColor(total) {
  if (total >= 85) return "text-emerald-400";
  if (total >= 60) return "text-amber-400";
  return "text-severity-critical";
}

export default function ScorePanel({ score, summary }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
          Code quality score
        </h2>
        <span className={`text-3xl font-bold ${scoreColor(score.total)}`}>
          {score.total}
          <span className="text-base text-slate-500">/100</span>
        </span>
      </div>

      <ul className="mt-3 space-y-1 text-sm text-slate-300">
        {PENALTY_ROWS.map(({ key, label }) => (
          <li key={key} className="flex justify-between">
            <span>{label}</span>
            <span className={score[key] > 0 ? "text-severity-high" : "text-slate-500"}>
              {score[key] > 0 ? `-${score[key]}` : "0"}
            </span>
          </li>
        ))}
        <li className="flex justify-between border-t border-slate-800 pt-1 font-medium text-slate-200">
          <span>Base</span>
          <span>{score.base}</span>
        </li>
      </ul>

      {summary && <p className="mt-3 text-xs text-slate-500">{summary}</p>}
    </div>
  );
}
