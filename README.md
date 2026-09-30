# 🔍 Blast Radius Prediction Engine

> **Predict the potential impact of a code change before it reaches production.**

The **Blast Radius Prediction Engine** is a Python-based static and historical code analysis tool that identifies potentially affected functions and files when a function is modified.

It combines **structural dependencies, Git history, and test coverage** to estimate the potential blast radius and generate an explainable risk assessment.

---

## 🚀 Overview

A small change in one function can affect multiple parts of a software system.

For example:

```text
Function A
   │
   ├── called by → Function B
   │                 │
   │                 └── used by → Module C
   │
   └── historically changes with → Module D
