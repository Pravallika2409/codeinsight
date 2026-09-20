import SeverityBadge from "./SeverityBadge.jsx";

const SOURCE_LABEL = {
  "static-analysis": "Static analysis",
  compiler: "Compiler",
  ai: "AI (not a guaranteed bug)",
  "complexity-analysis": "Complexity analysis",
};

export default function FindingCard({ finding }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4 space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-semibold text-slate-100">{finding.message}</h3>
        <SeverityBadge severity={finding.severity} />
      </div>

      <div className="flex flex-wrap gap-3 text-xs text-slate-400">
        <span>Category: {finding.category}</span>
        {finding.line != null && <span>Line {finding.line}{finding.column != null ? `:${finding.column}` : ""}</span>}
        <span>{finding.file}</span>
        <span className="italic">{SOURCE_LABEL[finding.source] || finding.source}</span>
      </div>

      {finding.explanation && (
        <p className="text-sm text-slate-300">
          <span className="font-medium text-slate-200">What/why: </span>
          {finding.explanation}
        </p>
      )}

      {finding.why_it_matters && (
        <p className="text-sm text-slate-300">
          <span className="font-medium text-slate-200">Why it matters: </span>
          {finding.why_it_matters}
        </p>
      )}

      {finding.suggestion && (
        <p className="text-sm text-slate-300">
          <span className="font-medium text-slate-200">Suggested fix: </span>
          {finding.suggestion}
        </p>
      )}

      {finding.improved_code && (
        <pre className="mt-2 overflow-x-auto rounded bg-slate-950 p-3 text-xs text-emerald-300">
          <code>{finding.improved_code}</code>
        </pre>
      )}
    </div>
  );
}
