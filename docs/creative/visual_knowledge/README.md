# Continuum Visual Knowledge

This folder defines the visual-knowledge layer that sits between story/canon and the panel renderer.

The goal is not to teach one model "everything about manga." Continuum should separate:

1. **Visual Knowledge** — reusable examples of how visual problems are solved.
2. **House Style** — the evolving default visual language of a project such as `The Arrivals`.
3. **Scene Treatment** — a deliberate temporary rendering treatment for one scene/sequence.
4. **Layered Construction** — the controlled order in which a panel is built and reviewed.

## Index

- [Navigation index](./INDEX.md)

- [Architecture](./VISUAL_KNOWLEDGE_LAYERED_RENDERER_ARCHITECTURE_v0.1.md)
- [The Arrivals House Style working direction](./THE_ARRIVALS_HOUSE_STYLE_WORKING_v0.1.md)
- [Visual Knowledge item schema](./VISUAL_KNOWLEDGE_ITEM_SCHEMA_v0.1.json)
- [External dataset audit](./EXTERNAL_DATASET_AUDIT_v0.1.md)
- [Dataset registry](./dataset_registry_v0.1.json)
- [Implementation backlog](./IMPLEMENTATION_BACKLOG_v0.1.md)
- [Renderer benchmark plan](./MANGA_RENDERER_BENCHMARK_PLAN_v0.1.md)
- [Claude return handoff](./CLAUDE_RETURN_HANDOFF_v0.1.md)
- [Work test plan](./WORK_TEST_PLAN_v0.1.md)

## Storage rule

No copyrighted source bytes belong in Git.

Git stores:
- architecture;
- manifests;
- metadata;
- schemas;
- decisions;
- URLs/licenses;
- benchmarks;
- code.

Source media remains in configured local roots / read-only intake locations. Derived artifacts remain in Continuum's writable content-addressed roots.

## Chibi

Chibi / super-deformed is already conceptually present as `VisualModeCategory.COMEDIC_DEFORMATION`.

It is intentionally **not urgent**. Treat it as a character/scene visual mode:
- same identity;
- intentionally changed proportions;
- separate reference subset;
- no contamination of normal identity training.
