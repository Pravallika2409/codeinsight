import { Link } from "react-router-dom";

export default function Landing() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
      <h1 className="text-4xl font-bold text-slate-100 sm:text-5xl">
        CodeInsight AI
      </h1>
      <p className="max-w-xl text-slate-400">
        AI-assisted code review built on real static analysis: deterministic
        checks from cppcheck and Python's AST first, AI explanations layered
        on top — never the other way around.
      </p>
      <Link
        to="/analyzer"
        className="rounded-lg bg-indigo-600 px-6 py-3 font-semibold text-white hover:bg-indigo-500"
      >
        Try the analyzer
      </Link>
      <p className="text-xs text-slate-600">
        Phase 1: C++ and Python static analysis. Accounts, history, and AI
        explanations land in later phases.
      </p>
    </div>
  );
}
