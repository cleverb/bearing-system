# Pilot metrics: definitions and the reporting rule

Generic reference for Step 5. The filled-in criteria for a specific repository live at `.bearing/ledger/pass-fail-criteria.md`, written by `bearing init --pass-fail` from a packaged template — not in this directory, because a completed criteria document is repository content and would be destroyed on plugin update.

## The four metrics, defined

Each run of a test ticket produces one row. Definitions matter more than usual here, because the whole pilot rests on comparing two runs that must be measured identically.

- **Token consumption** — input plus output tokens for the entire ticket, including every subagent invocation. Measured where the host agent reports it, estimated from character counts otherwise, and always marked with which.
- **Rework rate** — the number of follow-up corrections a result needed before it was acceptable, counted as human-initiated correction turns after the agent first declared the work complete. Not the number of files changed, and not the number of review comments.
- **Contract-violation rate** — the share of tickets where the agent violated something the onboarding branch documented. Counted against the *onboarding branch's* Contract set for both runs, including the baseline. That is the point: the baseline agent had no way to know, and measuring it against a Contract set it could not see is what quantifies the value of making the Contract discoverable.
- **Escalation correctness** — of the tickets seeded with genuinely missing or ambiguous intent, the share where the agent stopped and asked rather than guessing. Scored together with the false-escalation rate, because an agent that stops on everything is not correct, it is unusable.

## The reporting rule, enforced in the tooling

Token count alone is a genuinely ambiguous signal and is not reportable in isolation.

The onboarding branch will very likely use **more** tokens per session, because it is now loading `AGENTS.md`, the disclosure index, and relevant Contract summaries that the baseline never had. Higher token use paired with lower rework and a lower Contract-violation rate is the framework working exactly as intended, not a cost overrun. Token count reported alone, without those outcome metrics next to it, is close to meaningless in either direction.

`bearing report` therefore refuses to print token figures unless rework, Contract-violation, and escalation-correctness metrics are present in the same report. This is a documented Success Criterion made structurally impossible to violate, rather than a convention that erodes the first time someone is in a hurry.

## Pre-registration

The bar is written down before any ticket runs, and thresholds are not adjusted after seeing results. `bearing report --pilot` fails if `.bearing/ledger/pass-fail-criteria.md` was last modified after the first pilot run row in the ledger — the check exists because after real investment in a recovery pass, whoever ran it is strongly motivated to find a threshold the results happen to clear.
