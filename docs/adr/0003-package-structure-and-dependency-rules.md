# 0003. Package structure and dependency rules

- **Status:** Accepted
- **Date:** 2026-10-25

## Context

The app will grow (streaming, documents, retrieval, agents). In Python, circular
imports fail when modules load, and there is no package-private visibility, so the
structure must follow dependency direction and the rules must be checked.

## Decision

- **Shared layers plus one package per capability:**
  ```
  app/
    main.py      composition root (create_app, lifespan)
    core/        config, logging setup
    api/         routers, dependencies, exception handlers
    schemas/     request/response models
    llm/         types, errors, factory, providers/
    services/    business logic (e.g. RAG orchestration)
  tests/         mirrors app/
  ```
- **Dependency rules**, enforced by `tests/test_architecture.py`:

  | Package | May import from |
  | --- | --- |
  | `core` | nothing else in `app/` |
  | `schemas` | `core` |
  | `llm` | `core` (inside it, `providers/` only `llm.types` and `llm.errors`) |
  | `services` | `core`, `llm`, `schemas` |
  | `api` | `core`, `llm`, `schemas`, `services` |
  | `main.py` | everything |

- **Each package's `__init__.py` is its public API** (`__all__`). Outside callers use
  `from app.llm import ...`; modules inside the package import specific submodules.
- **Naming:** LLM implementations are *providers*; "service" is reserved for business
  logic. Avoid `Impl`, `utils` and module names that shadow the standard library.

## Why

- One-way dependencies prevent circular imports and keep layers replaceable.
- A test enforces the rules, because documented rules alone drift.
- A public API per package lets its internals change without breaking callers.

## Alternatives considered

- **Flat layout** - works for very small apps; does not scale to upcoming features.
- **Strict package-by-feature** - premature with a single endpoint; capabilities can
  evolve towards it.
- **One class per file** - not idiomatic Python; modules group related code.

## Consequences

- A new package needs a rule in `tests/test_architecture.py`, or CI fails.
- Logger names follow module paths, so log filters change when modules move.
- Add layers only when there is code to put in them.
