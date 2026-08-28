# Blast Radius Prediction Engine

A static-analysis tool that predicts the **risk and potential blast radius of a Python function change** before the change is merged.

The engine combines structural code analysis, Git history, and test coverage to identify potentially affected functions and calculate an overall risk score.

---

## Overview

A seemingly small change in a codebase can affect multiple functions or files through dependencies, historical relationships, and insufficient test coverage.

The **Blast Radius Prediction Engine** analyzes these factors before a change is merged and provides an interpretable risk assessment.

The system currently supports Python projects.

### Core Analysis Signals

The engine combines three major signals:

1. **Structural Analysis**
   - Parses Python source code using Tree-sitter.
   - Identifies functions and function calls.
   - Builds a function-level call graph.
   - Determines direct and transitive dependencies.

2. **Historical Analysis**
   - Mines Git commit history.
   - Identifies files that frequently change together.
   - Uses historical co-change information as a risk signal.

3. **Test Coverage Analysis**
   - Reads coverage information.
   - Determines coverage associated with the analyzed function.
   - Treats insufficient coverage as additional risk.

These signals are combined by the risk-scoring system and exposed through the prediction engine and CLI.

---

## Problem Statement

In a large software project, changing one function can unintentionally affect many other parts of the system.

Developers usually need to manually inspect:

- Function dependencies
- Call relationships
- Previously co-changed files
- Test coverage
- Potentially affected components

This manual process can become difficult and error-prone as the codebase grows.

The **Blast Radius Prediction Engine** aims to automate this analysis and provide an early warning about potentially risky changes.

---

## Objectives

The main objectives of the project are:

- Analyze the structure of a Python project.
- Build a function-level dependency graph.
- Identify affected functions.
- Analyze historical file co-change patterns.
- Analyze test coverage.
- Combine multiple signals into a risk score.
- Classify the change into a risk level.
- Provide an easy-to-use command-line interface.
- Produce explainable results rather than only a single risk value.

---

## System Architecture

```text
                         Python Project
                               |
                               v
                     +-------------------+
                     |    AST Parser     |
                     +-------------------+
                               |
                               v
                     +-------------------+
                     |    Call Graph     |
                     +-------------------+
                               |
                +--------------+--------------+
                |                             |
                v                             v
        Structural Analysis          Affected Functions
                |                             |
                +--------------+--------------+
                               |
              +----------------+----------------+
              |                                 |
              v                                 v
       Git History Miner                Coverage Analyzer
              |                                 |
              v                                 v
      Historical Signal                  Coverage Signal
              |                                 |
              +----------------+----------------+
                               |
                               v
                     +-------------------+
                     |    Risk Scorer    |
                     +-------------------+
                               |
                               v
                     +-------------------+
                     | Prediction Engine |
                     +-------------------+
                               |
                               v
                     +-------------------+
                     |       CLI         |
                     +-------------------+
                               |
                               v
                         Risk Report