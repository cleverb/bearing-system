# BEARING: An EOCR-Based Decision System — moved

The full architecture document is canonical at [`/BEARING.md`](../../BEARING.md) in the repository root.

This file used to hold a byte-identical second copy. That made the framework's own constitution a document with two sources of truth, which is exactly what Part IV of that document forbids:

> Never let a generated file become a second source of truth.

A duplicate is worse than a projection — a projection at least has a renderer and a drift check. So the duplicate is gone rather than automated. `BEARING.md` sits at the repository root because it is Entry-surface knowledge that both humans and agents are pointed to from [`/AGENTS.md`](../../AGENTS.md) and [`/README.md`](../../README.md), and root is where an agent entering the repository looks first.

The other documents in this directory remain the authoritative specs for their individual Skills:

- [`decision-recovery-skill-spec.md`](decision-recovery-skill-spec.md)
- [`decision-interview-skill-spec.md`](decision-interview-skill-spec.md)
- [`decision-onboarding-skill-spec.md`](decision-onboarding-skill-spec.md)
- [`bearing-distribution-spec.md`](bearing-distribution-spec.md) — the distribution, config, and projection layers

`bearing verify --docs` checks that every path referenced across these documents actually exists, so this pointer stays honest if the layout changes again.
