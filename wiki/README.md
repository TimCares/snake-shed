# Project Wiki

An LLM-maintained wiki for project documentation, including
decisions, guides, reference material, and a running journal of thoughts and observations.
The LLM handles the bookkeeping (cross-references, metadata, index updates) so that writing documentation never feels like a chore.

Inspired by [Karpathy's LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) and [llm-context-base](https://github.com/asakin/llm-context-base), scoped to project-level concerns.

---

## Structure

```text
wiki/
  index.md              Catalog of all pages (read this first)
  log.md                Append-only timeline of wiki activity
  inbox/                Quick capture zone — triage within ~7 days
  decisions/            Architecture Decision Records (ADRs)
  guides/               How-tos, runbooks, setup instructions
  reference/            Architecture docs, specs, conventions
  journal/              Thoughts, observations, findings — a project daybook
  _templates/           Templates for each document type
```

---

## Metadata Standard

Every wiki page (except templates, READMEs, and agent files) gets YAML frontmatter at the top:

```yaml
---
type: decision | guide | reference | journal
summary: "One sentence — what this file covers."
tags: [architecture, deployment, config]
status: active | draft | archived | superseded
updated: YYYY-MM-DD
related: "[other-file](../path/to-file.md)"
---
```

**Required fields:** `type`, `summary`, `tags`, `status`, `updated`.

**Optional field:** `related` — cross-links to other wiki pages.

The `summary` field is the most important — the LLM reads summaries to find relevant pages without loading entire files.

---

## How to Use

### Capture something quickly

Tell the LLM: *"capture this: [content]"*. It creates a file in `inbox/` using the inbox-capture template. You can file it properly later, or the LLM can do it during triage.

### Record a decision

Tell the LLM: *"document why we chose X over Y"*. It uses the decision template to record context, options, rationale, and trade-offs.

### Write a guide

Tell the LLM: *"write a guide for how to deploy"*. It uses the guide template with prerequisites and step-by-step instructions.

### Add reference material

Tell the LLM: *"document our API conventions"*. It uses the reference template for specs, architecture docs, or conventions.

### Dump your thoughts

Tell the LLM: *"I just noticed that..."* or *"here's what I'm thinking about..."*. It creates a journal entry — low-ceremony, no structure required. Think of it as a project daybook or engineering lab notebook. Multiple entries per day are fine.

### After any write

The LLM updates `index.md` with a link and summary, and appends an entry to `log.md`.

---

## Inbox

Files land here when you want to capture something but don't know where it belongs yet. Named `YYYY-MM-DD-short-slug.md`. Items older than 7 days get flagged during lint for triage into `decisions/`, `guides/`, `reference/`, or `journal/`.

---

## Journal

A running narrative of observations, findings, and thoughts about the project. Unlike inbox items (which are temporary and get filed elsewhere), journal entries are permanent — they stay in `journal/` as a timeline of what you were thinking and why. Useful for:

- Observations while debugging ("this API behaves oddly when...")
- Design thinking ("I'm leaning toward X because...")
- Things you learned ("turns out the bottleneck was...")
- Status narration ("spent today refactoring the config layer, here's where things stand")

---

## Wiki Lint

Ask the LLM to *"lint the wiki"* or *"wiki health check"*. It runs these checks:

1. **Stale inbox** — items in `inbox/` older than 7 days
2. **Missing metadata** — files without YAML frontmatter
3. **Stale active files** — `status: active` but `updated` older than 90 days (journal entries are exempt)
4. **Orphaned files** — pages with no inbound links from any other page (journal entries are exempt)
5. **Index drift** — files that exist on disk but are missing from `index.md`

Results are appended to `log.md`.

---

## Log Format

Each entry in `log.md` uses a parseable format:

```markdown
## [YYYY-MM-DD] action | Short description
```

Actions: `create`, `update`, `archive`, `lint`.

---

## Templates

Templates live in `_templates/` and define the structure for each document type:

- `decision.md` — Context, options with pros/cons, rationale, outcome tracking
- `guide.md` — Overview, prerequisites, step-by-step instructions
- `reference.md` — Overview, main content, related resources
- `journal.md` — Freeform thoughts and observations
- `inbox-capture.md` — Minimal capture for quick notes
