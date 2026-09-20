import { useState, useMemo, useEffect } from "react";
import Editor from "@monaco-editor/react";
import { analyzeCode, listProjects, ApiError } from "../services/api.js";
import AnalysisResultsPanel from "../components/AnalysisResultsPanel.jsx";
import { useAuth } from "../context/AuthContext.jsx";

const LANGUAGES = [
  { value: "cpp", label: "C++", monacoId: "cpp", placeholder: DEFAULT_CPP() },
  { value: "python", label: "Python", monacoId: "python", placeholder: DEFAULT_PY() },
  { value: "javascript", label: "JavaScript", monacoId: "javascript", placeholder: DEFAULT_JS() },
  { value: "java", label: "Java", monacoId: "java", placeholder: DEFAULT_JAVA() },
];

const FILE_EXTENSION = { cpp: "cpp", python: "py", javascript: "js", java: "java" };

function DEFAULT_CPP() {
  return `#include <iostream>

int main() {
    int *ptr = nullptr;
    std::cout << *ptr << std::endl;
    return 0;
}
`;
}

function DEFAULT_PY() {
  return `def process(items, cache={}):
    cache[len(items)] = items
    return cache
`;
}

function DEFAULT_JS() {
  return `function run(userInput) {
    if (userInput == "1") {
        eval(userInput);
    }
    var unused = 42;
    return true;
}
`;
}

function DEFAULT_JAVA() {
  return `import java.io.FileReader;

public class Submission {
    public void readFile() {
        try {
            FileReader fr = new FileReader("data.txt");
            int c = fr.read();
            System.out.println(c);
        } catch (Exception e) {
        }
    }
}
`;
}

export default function CodeAnalyzer() {
  const [language, setLanguage] = useState("cpp");
  const [code, setCode] = useState(DEFAULT_CPP());
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [includeAiReview, setIncludeAiReview] = useState(false);
  const { isAuthenticated } = useAuth();

  const currentLanguage = useMemo(
    () => LANGUAGES.find((l) => l.value === language),
    [language]
  );

  useEffect(() => {
    if (isAuthenticated) {
      listProjects().then(setProjects).catch(() => setProjects([]));
    } else {
      setProjects([]);
      setSelectedProjectId("");
    }
  }, [isAuthenticated]);

  function handleLanguageChange(next) {
    setLanguage(next);
    setResult(null);
    setError(null);
    const preset = LANGUAGES.find((l) => l.value === next);
    setCode(preset ? preset.placeholder : "");
  }

  function handleClear() {
    setCode("");
    setResult(null);
    setError(null);
  }

  async function handleAnalyze() {
    setIsAnalyzing(true);
    setError(null);
    try {
      const response = await analyzeCode({
        code,
        language,
        filename: `submitted_code.${FILE_EXTENSION[language] ?? "txt"}`,
        project_id: selectedProjectId ? Number(selectedProjectId) : undefined,
        include_ai_review: includeAiReview,
      });
      setResult(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unexpected error while analyzing code.");
      setResult(null);
    } finally {
      setIsAnalyzing(false);
    }
  }

  return (
    <div className="grid flex-1 grid-cols-1 gap-4 p-4 lg:grid-cols-2">
      {/* LEFT: editor */}
      <section className="flex flex-col rounded-lg border border-slate-800 bg-slate-900/40">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 p-3">
          <div className="flex items-center gap-2">
            <select
              value={language}
              onChange={(e) => handleLanguageChange(e.target.value)}
              className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
              aria-label="Select language"
            >
              {LANGUAGES.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
            {isAuthenticated && projects.length > 0 && (
              <select
                value={selectedProjectId}
                onChange={(e) => setSelectedProjectId(e.target.value)}
                className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-sm text-slate-200"
                aria-label="Save to project"
              >
                <option value="">Don't save</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    Save to: {p.name}
                  </option>
                ))}
              </select>
            )}
          </div>
          <button
            onClick={handleClear}
            className="rounded border border-slate-700 px-3 py-1 text-sm text-slate-300 hover:bg-slate-800"
          >
            Clear
          </button>
        </header>
        <div className="min-h-[420px] flex-1">
          <Editor
            height="100%"
            language={currentLanguage?.monacoId}
            value={code}
            onChange={(value) => setCode(value ?? "")}
            theme="vs-dark"
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              scrollBeyondLastLine: false,
            }}
          />
        </div>
      </section>

      {/* RIGHT: results */}
      <section className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <button
            onClick={handleAnalyze}
            disabled={isAnalyzing || !code.trim()}
            className="flex-1 rounded-lg bg-indigo-600 px-4 py-2 font-semibold text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isAnalyzing ? "Analyzing…" : "Analyze code"}
          </button>
          <label className="flex shrink-0 items-center gap-1.5 text-xs text-slate-400" title="Requires an AI provider to be configured on the server; degrades gracefully if not.">
            <input
              type="checkbox"
              checked={includeAiReview}
              onChange={(e) => setIncludeAiReview(e.target.checked)}
              className="accent-indigo-600"
            />
            AI review
          </label>
        </div>

        {error && (
          <div className="rounded-lg border border-severity-critical/40 bg-severity-critical/10 p-3 text-sm text-severity-critical">
            {error}
          </div>
        )}

        {result?.analysis_id && (
          <p className="text-xs text-emerald-400">Saved to project (analysis #{result.analysis_id}).</p>
        )}

        {result && <AnalysisResultsPanel result={result} />}

        {!result && !error && (
          <p className="text-sm text-slate-500">
            Write or paste code on the left, then click Analyze to run static
            analysis and get an explainable quality report.
            {!isAuthenticated && " Log in to save results to a project."}
          </p>
        )}
      </section>
    </div>
  );
}
