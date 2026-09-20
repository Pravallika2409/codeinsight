// Fixed lint configuration used by app/analyzers/javascript_analyzer.py.
// This is NOT the frontend's lint config -- it's a standalone ruleset the
// backend shells out to for analyzing arbitrary *submitted* JS snippets,
// so it deliberately avoids requiring a package.json/project context near
// the code being analyzed (--no-config-lookup is passed at call time).
import globals from "globals";

export default [
  {
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
        ...globals.es2021,
      },
    },
    rules: {
      // Unused variables
      "no-unused-vars": "warn",

      // Equality issues
      eqeqeq: "error",
      "no-cond-assign": "error",

      // Potential undefined / unsafe access
      "no-undef": "error",
      "no-unsafe-optional-chaining": "error",
      "no-unsafe-negation": "error",

      // Dangerous eval usage
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",

      // Promise-related issues
      "no-async-promise-executor": "error",
      "no-promise-executor-return": "error",
      "require-atomic-updates": "error",

      // Basic security issues
      "no-script-url": "error",

      // Complexity-adjacent code smells
      "no-var": "warn",
      "no-fallthrough": "error",
      "no-unreachable": "error",
    },
  },
];
