---
id: ADR-0005
status: Accepted
eocr_function: Contract
trigger: adding a Python dependency, raising the minimum interpreter, or replacing the in-tree JSON Schema validator
scope: plugin/src/bearing/*.py
---

# ADR-0005: Standard library only, Python 3.9

* **Date:** 2026-08-18
* **Deciders:** BEARING maintainers
* **Tickets:**

## Context and Problem Statement

`bearing init` runs on a repository that has not installed a package manager environment for BEARING. A CLI that needs `pip install` first is a CLI that does not run at the moment of adoption.

## Decision Drivers

* Bootstrap on a bare Python 3.9.
* Config validation and JSONL checks must work without PyPI.

## Considered Options

1. Depend on pydantic, jsonschema, PyYAML, and pytest.
2. Zero third-party dependencies; in-tree subset parsers; stdlib unittest.

## Decision Outcome

Chosen option: **2**. `plugin/pyproject.toml` declares `requires-python = ">=3.9"` and `dependencies = []`. The in-tree validator covers only the keywords BEARING's own schemas use.

## Consequences

* Front matter is a subset, not YAML. Complex YAML in an ADR may silently mis-parse.
* JSON Schema `$ref` is local (`#/$defs/...` or inlined sibling files), not remote.

## Deletion test

If a third-party package becomes required, `bearing init` on a locked-down laptop or CI image without that package fails before the decision system can start. Adoption friction returns as a runtime error.
