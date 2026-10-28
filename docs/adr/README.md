# Architecture Decision Records

Significant architectural decisions for KnowledgePilot AI, recorded as
**ADRs** (Architecture Decision Records): what we decided, why, and the trade-offs.

## Index

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-provider-neutral-llm-abstraction.md) | Provider-neutral LLM abstraction | Accepted |
| [0002](0002-factories-and-application-lifecycle.md) | Factories and application lifecycle | Accepted |
| [0003](0003-package-structure-and-dependency-rules.md) | Package structure and dependency rules | Accepted |
| [0004](0004-testing-strategy.md) | Testing strategy | Accepted |
| [0005](0005-streaming-chat-protocol.md) | Streaming chat protocol | Accepted |
| [0006](0006-request-correlation-and-latency-logging.md) | Request correlation and latency logging | Proposed |

## When to write an ADR

Write one when a decision:

- is hard or expensive to reverse (structure, frameworks, data formats, APIs),
- affects how other code must be written (layering rules, error conventions),
- has security or cost implications (secrets, logging, paid API calls), or
- was debated, so that the reasoning is not lost.

Small, local choices (naming a variable, a helper function) do not need one.

## How to add one

1. Copy [`template.md`](template.md) to `NNNN-short-title.md` using the next number.
2. Fill it in with status **Proposed** and open a PR; discuss it there.
3. When the PR is merged, set the status to **Accepted** and add it to the index above.
4. Accepted ADRs are not rewritten. To change a decision, write a new ADR, set the
   old one's status to **Superseded by ADR-NNNN**, and link both ways.
