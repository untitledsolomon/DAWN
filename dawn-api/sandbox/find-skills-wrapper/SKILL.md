---
name: find-skills
description: Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extending capabilities.
---

# Find Skills

This skill helps you discover and install skills from the open agent skills ecosystem.

## When to Use This Skill

Use this skill when the user:
- Asks "how do I do X" where X might be a common task with an existing skill
- Says "find a skill for X" or "is there a skill for X"
- Asks "can you do X" where X is a specialized capability
- Expresses interest in extending agent capabilities
- Wants to search for tools, templates, or workflows
- Mentions they wish they had help with a specific domain (design, testing, deployment, etc.)

## What is the Skills CLI?

The Skills CLI (`npx skills`) is the package manager for the open agent skills ecosystem. Skills are modular packages that extend agent capabilities with specialized knowledge, workflows, and tools.

**Key commands:**
- `npx skills find [query] [--owner <owner>]` - Search for skills interactively or by keyword
- `npx skills add <package>` - Install a skill from GitHub or other sources
- `npx skills check` - Check for skill updates
- `npx skills update` - Update all installed skills

**Browse skills at:** https://skills.sh/

## How to Help Users Find Skills

### Step 1: Understand What They Need
Identify the domain, specific task, and whether a skill likely exists.

### Step 2: Check the Leaderboard First
Check https://skills.sh/ for well-known skills before running a CLI search.

### Step 3: Search for Skills
Run `npx skills find [query] [--owner <owner>]` to discover relevant skills.

### Step 4: Verify Quality Before Recommending
Check install count (prefer 1K+), source reputation, and GitHub stars.

### Step 5: Present Options
Show the skill name, what it does, install count, source, and install command.

### Step 6: Offer to Install
`npx skills add <owner/repo@skill> -g -y` to install globally.

## Common Skill Categories
| Category | Example Queries |
|----------|----------------|
| Web Development | react, nextjs, typescript, css, tailwind |
| Testing | testing, jest, playwright, e2e |
| DevOps | deploy, docker, kubernetes, ci-cd |
| Documentation | docs, readme, changelog, api-docs |
| Code Quality | review, lint, refactor, best-practices |
| Design | ui, ux, design-system, accessibility |
| Productivity | workflow, automation, git |

## When No Skills Are Found
Acknowledge no skill was found, offer to help directly, suggest creating a skill with `npx skills init`.
