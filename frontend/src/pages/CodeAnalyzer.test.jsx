import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import CodeAnalyzer from "./CodeAnalyzer.jsx";
import { AuthProvider } from "../context/AuthContext.jsx";

// Monaco doesn't render meaningfully in jsdom; stub it so this stays a fast
// unit test of our own component logic rather than an editor integration test.
vi.mock("@monaco-editor/react", () => ({
  default: ({ value, onChange }) => (
    <textarea
      data-testid="mock-editor"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
}));

function renderWithAuth(ui) {
  return render(<AuthProvider>{ui}</AuthProvider>);
}

describe("CodeAnalyzer", () => {
  it("renders the analyze button and language selector", () => {
    renderWithAuth(<CodeAnalyzer />);
    expect(screen.getByText(/analyze code/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/select language/i)).toBeInTheDocument();
  });

  it("shows the empty-state hint before any analysis has run", () => {
    renderWithAuth(<CodeAnalyzer />);
    expect(screen.getByText(/write or paste code/i)).toBeInTheDocument();
  });

  it("offers all four Phase 1+2 languages in the selector", () => {
    renderWithAuth(<CodeAnalyzer />);
    const select = screen.getByLabelText(/select language/i);
    const optionLabels = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(optionLabels).toEqual(["C++", "Python", "JavaScript", "Java"]);
  });

  it("offers an opt-in AI review checkbox, unchecked by default", () => {
    renderWithAuth(<CodeAnalyzer />);
    const checkbox = screen.getByRole("checkbox", { name: /ai review/i });
    expect(checkbox).not.toBeChecked();
  });
});
