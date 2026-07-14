"""
Sub-Agent Framework for DAWN v37.0.

Architecture:
  Supervisor Agent (DAWN main loop)
    ├── crm_agent      → CRM operations (leads, deals, pipeline, team)
    ├── ops_agent      → Infrastructure, deployments, monitoring
    ├── research_agent → Web search, knowledge graph, competitive intel
    ├── code_agent     → Filesystem, git, terminal operations
    ├── comms_agent    → Email, Slack broadcasts, scheduling
    ├── data_agent     → BI, charts, revenue analysis
    ├── axis_agent     → Payroll, tax, URA compliance (Axis ERP)
    ├── forge_agent    → CMS content management (Forge)
    └── security_agent → OSINT, pentest, audit, compliance

Each sub-agent has:
  - A YAML definition file (name, description, allowed tools, system prompt)
  - An isolated agent loop with its own context window
  - Tool access restricted to its domain
  - Result-only return (no intermediate steps exposed to supervisor)

The supervisor delegates via delegate_to_subagent() or delegate_parallel() tools.
"""
