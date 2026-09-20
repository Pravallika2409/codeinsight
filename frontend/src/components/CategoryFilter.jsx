const CATEGORY_LABEL = {
  bug: "Bug",
  security: "Security",
  performance: "Performance",
  code_smell: "Code smell",
  maintainability: "Maintainability",
  complexity: "Complexity",
  style: "Style",
};

export default function CategoryFilter({ categories, active, onChange }) {
  if (categories.length <= 1) return null;

  return (
    <div className="flex flex-wrap gap-1.5">
      <button
        onClick={() => onChange("all")}
        className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
          active === "all"
            ? "border-indigo-500 bg-indigo-600/20 text-indigo-300"
            : "border-slate-700 text-slate-400 hover:border-slate-600"
        }`}
      >
        All
      </button>
      {categories.map((cat) => (
        <button
          key={cat}
          onClick={() => onChange(cat)}
          className={`rounded-full border px-3 py-1 text-xs font-medium transition ${
            active === cat
              ? "border-indigo-500 bg-indigo-600/20 text-indigo-300"
              : "border-slate-700 text-slate-400 hover:border-slate-600"
          }`}
        >
          {CATEGORY_LABEL[cat] || cat}
        </button>
      ))}
    </div>
  );
}
