const SEGMENT_STYLE = {
  critical: "bg-severity-critical",
  high: "bg-severity-high",
  medium: "bg-severity-medium",
  low: "bg-severity-low",
  info: "bg-severity-info",
};

const ORDER = ["critical", "high", "medium", "low", "info"];

export default function SeverityBar({ counts }) {
  const total = ORDER.reduce((sum, sev) => sum + (counts[sev] || 0), 0);

  if (total === 0) {
    return <div className="h-2 w-full rounded-full bg-slate-800" />;
  }

  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-slate-800">
      {ORDER.map((sev) =>
        counts[sev] > 0 ? (
          <div
            key={sev}
            className={SEGMENT_STYLE[sev]}
            style={{ width: `${(counts[sev] / total) * 100}%` }}
            title={`${sev}: ${counts[sev]}`}
          />
        ) : null
      )}
    </div>
  );
}
