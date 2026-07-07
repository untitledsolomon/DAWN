"""Decision Intelligence Engine

Constraint-based decision workflows with deterministic scoring,
simulation capabilities, and audit trail integration.

Architecture:
  - constraints.py: Hard/soft constraint evaluation primitives
  - scoring.py: Weighted ranking with tradeoff summaries
  - registry.py: Workflow registry with approval gate enforcement
  - simulate.py: What-if scenario execution (reuses constraint engine)
  - workflows/: Concrete decision workflow implementations
"""
