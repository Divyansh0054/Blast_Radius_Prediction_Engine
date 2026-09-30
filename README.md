# 🔍 Blast Radius Prediction Engine

> **Predict the potential impact of a code change before it reaches production.**

The **Blast Radius Prediction Engine** is an explainable Python-based static analysis and code change risk analysis tool that identifies potentially affected code elements when a function or method is modified.

The system combines **structural dependencies, historical Git co-change patterns, and test coverage information** to estimate the potential blast radius and prioritize risky code changes.

---

## 🎯 Objective

The primary objective of the project is to answer:

> **"If this function changes, what other parts of the codebase could be affected, and how risky is the change?"**

The system analyzes a target function and:

- Identifies functions that depend on the changed function.
- Traverses the source-code dependency graph.
- Analyzes historical Git co-change patterns.
- Examines test coverage of affected code.
- Calculates an explainable risk score.
- Produces a list of potentially affected files and functions.
- Provides evidence explaining why a change is considered risky.

---

# 🏗️ System Architecture

```text
                         ┌─────────────────────────┐
                         │      Target Change      │
                         │   Function / Method     │
                         └────────────┬────────────┘
                                      │
                                      ▼
                    ┌──────────────────────────────────┐
                    │       Source Code Analysis       │
                    │                                  │
                    │  • Tree-sitter / Python AST     │
                    │  • Function Extraction           │
                    │  • Call Extraction               │
                    │  • Import Analysis               │
                    │  • Dependency Detection          │
                    └───────────────┬──────────────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Dependency Graph  │
                         │                     │
                         │ Functions → Calls  │
                         │ Callers / Callees  │
                         └──────────┬──────────┘
                                    │
                  ┌─────────────────┼──────────────────┐
                  │                 │                  │
                  ▼                 ▼                  ▼
        ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
        │   Structural    │ │    Historical   │ │  Test Coverage  │
        │    Analysis     │ │     Analysis    │ │    Analysis     │
        │                 │ │                 │ │                 │
        │ Call Graph      │ │ Git History     │ │ Coverage Data   │
        │ Dependencies    │ │ Co-change       │ │ Tested Paths    │
        │ Reachability    │ │ Patterns        │ │ Untested Code  │
        └────────┬────────┘ └────────┬────────┘ └────────┬────────┘
                 │                   │                   │
                 └───────────────────┼───────────────────┘
                                     ▼
                         ┌─────────────────────┐
                         │    Risk Scoring    │
                         │                     │
                         │ Structural         │
                         │ Historical         │
                         │ Coverage           │
                         └──────────┬──────────┘
                                    │
                                    ▼
                       ┌────────────────────────┐
                       │   Blast Radius Report  │
                       │                        │
                       │ • Affected Functions   │
                       │ • Affected Files       │
                       │ • Risk Score           │
                       │ • Risk Level           │
                       │ • Supporting Evidence  │
                       └────────────────────────┘
