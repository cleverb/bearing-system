---
id: ADR-0011
status: Accepted
eocr_function: Contract
trigger: claiming that a runtime client is supported by a BEARING release
scope: plugin/src/bearing/compatibility.py, plugin/src/bearing/doctor.py, plugin/src/bearing/manifests.py, scripts/conformance/**
---

# ADR-0011: Real-client conformance qualifies runtime support

* **Date:** 2026-08-18
* **Deciders:** BEARING maintainers
* **Tickets:**

## Context and Problem Statement

Static manifest and copy-isolation checks prove that BEARING's package is
self-consistent. They do not prove that a released client accepts the package,
discovers its Skills, loads its adapters, or executes its declared hooks.

## Decision Drivers

* Runtime formats are fast-moving Distribution interfaces, not canonical organizational semantics.
* A support claim must name the evidence behind it.
* Unrelated changes must not invalidate runtime evidence needlessly.

## Considered Options

1. Infer client support from schema reading and internal package tests.
2. Qualify support with real-client evidence bound to compatibility inputs and exercised artifacts.

## Decision Outcome

Chosen option: **2**. A runtime is release-qualified only when current
conformance evidence covers its declared compatibility range and the relevant
BEARING compatibility API, renderer/schema versions, and artifact hashes.
Client names, versions, commands, and lifecycle fields remain Distribution facts
outside this normative record.

## Consequences

* Client conformance gates release qualification, never unrelated source merges.
* Documentation-only and unrelated-adapter changes do not expire valid evidence.
* Runtime support can degrade without invalidating the EOCR model or decision corpus.

## Deletion test

Without this Contract, BEARING can publish a self-consistent package that every
supported client rejects while still describing the release as compatible.
