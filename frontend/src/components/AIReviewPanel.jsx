export default function AIReviewPanel({ aiReview }) {
  if (!aiReview) return null;

  return (
    <div className="rounded-lg border border-indigo-800/50 bg-indigo-950/30 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <span className="rounded-full bg-indigo-600/30 px-2 py-0.5 text-xs font-semibold uppercase tracking-wide text-indigo-300">
          AI review
        </span>
        <span className="text-xs text-slate-500">Suggestions, not guaranteed findings</span>
      </div>

      <p className="text-sm text-slate-200">{aiReview.summary}</p>
      <p className="text-sm text-slate-400">{aiReview.overall_assessment}</p>

      {aiReview.recommendations?.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Recommendations</h4>
          <ul className="space-y-1">
            {aiReview.recommendations.map((rec, i) => (
              <li key={i} className="text-sm text-slate-300">
                <span className="font-medium text-slate-200">{rec.title}:</span> {rec.description}
              </li>
            ))}
          </ul>
        </div>
      )}

      {aiReview.improved_code && (
        <div>
          <h4 className="mb-1 text-xs font-semibold uppercase text-slate-500">Suggested improved code</h4>
          <pre className="overflow-x-auto rounded bg-slate-950 p-3 text-xs text-emerald-300">
            <code>{aiReview.improved_code}</code>
          </pre>
        </div>
      )}
    </div>
  );
}
