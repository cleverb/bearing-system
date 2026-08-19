# Optional pilot metrics

These metrics can support a comparative evaluation. They are examples, not a
universal scorecard. A repository may use qualitative feedback, real-work
observations, different measurements, or no formal pilot at all.

- **Token consumption** — input plus output tokens for the work, labelled as
  measured or estimated where possible.
- **Rework** — follow-up corrections needed before the result was acceptable.
- **Contract violations** — cases where the result violated a documented
  Contract relevant to the work.
- **Escalation correctness** — whether the agent stopped for genuinely missing
  authority without escalating routine, resolved work.

Token count is easier to interpret beside outcomes because loading decision
context has a cost and may reduce rework or violations. `bearing report` warns
when paired outcome fields are absent but still shows the available data.

For teams running a controlled experiment, the supplied criteria template can
record the intended comparison before results are visible. `bearing report
--pilot` treats missing or late criteria as an advisory because BEARING does not
own the team's experimental protocol.
