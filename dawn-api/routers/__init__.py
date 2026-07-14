"""Decision Intelligence Engine

Data-driven, generic decision workflows and ontology object model.
Workflows and object types are rows in the database (ontology_workflows,
ontology_objects, ontology_relationships) — never one Python file per
workflow or one hardcoded table map per object type. Onboarding a new
client's domain, or a new workflow, is a data change.

Architecture:
  - ontology_engine.py: Generic object/relationship query engine, driven
      entirely by ontology_objects / ontology_relationships.
  - constraint_interpreter.py: Interprets JSON constraint specs (hard/soft
      rules) against candidate options — no per-workflow Python evaluators.
  - candidates.py: Generic candidate sourcing for workflows, including
      simulation snapshot support.
  - registry.py: Loads workflows from ontology_workflows into an in-memory
      cache and runs them via the constraint interpreter.
  - simulate.py: What-if scenario execution (reuses the same engine twice).
"""
