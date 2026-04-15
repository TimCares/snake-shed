# Wiki — Agent Instructions

You (the LLM) are the wiki maintainer. The human curates and directs, you handle all the bookkeeping: metadata, cross-references, index updates, and filing.

Read `index.md` first when answering questions about the project.

---

## Metadata Standard

Every wiki page (except templates, READMEs, and agent files) must have YAML frontmatter:

```yaml
---
type: decision | guide | reference | journal
summary: "One sentence — what this file covers."
tags: [tag1, tag2]
status: active | draft | archived | superseded
updated: YYYY-MM-DD
related: "[other-file](../path/to-file.md)"
---
```

Required: `type`, `summary`, `tags`, `status`, `updated`. Optional: `related`.

---

## Creating Wiki Pages

1. Determine the type (`decision`, `guide`, `reference`, or `journal`).
2. Copy the matching template from `_templates/`.
3. Fill in the frontmatter and content. Set `status: draft` for new pages (journal entries can go straight to `active`).
4. Save to the matching directory (`decisions/`, `guides/`, `reference/`, or `journal/`).
5. Update `index.md` — add a row to the correct section table with the filename link and summary.
6. Append to `log.md`: `## [YYYY-MM-DD] create | Short description`.

## Updating Wiki Pages

1. Edit the content.
2. Update the `updated:` field in frontmatter to today's date.
3. If the summary changed, update it in `index.md` too.
4. Append to `log.md`: `## [YYYY-MM-DD] update | Short description`.

---

## Inbox Captures

When the user says "capture this" or similar and the content doesn't have a clear home yet:

1. Create a file in `inbox/` named `YYYY-MM-DD-short-slug.md` using the inbox-capture template.
2. Offer to file it into the proper directory immediately, or leave it for later triage.
3. Do not add inbox items to `index.md` — they are temporary.

---

## Journal Entries

When the user wants to dump thoughts, observations, findings, or a narration of what they're working on:

1. Create a file in `journal/` named `YYYY-MM-DD-short-slug.md` using the journal template.
2. Journal entries are low-ceremony — no pressure to structure them. The value is in capturing the thought, not polishing it.
3. Multiple entries on the same day are fine — use distinct slugs.
4. Add journal entries to `index.md` like any other page.
5. When the user asks a question, journal entries are valid sources — past observations often contain relevant context.

---

## Wiki Lint

When the user says "lint the wiki", "wiki health check", or similar, run these checks in order:

1. **Stale inbox** — files in `inbox/` older than 7 days (by filename date or `updated` field).
2. **Missing metadata** — files in `decisions/`, `guides/`, `reference/`, `journal/` without YAML frontmatter.
3. **Stale active files** — `status: active` but `updated` older than 90 days. Journal entries are exempt (they are point-in-time by nature).
4. **Orphaned files** — wiki pages with no inbound links from any other wiki page. Journal entries are exempt.
5. **Index drift** — files on disk not listed in `index.md`, or index entries pointing to files that don't exist.

Report findings, then append to `log.md`: `## [YYYY-MM-DD] lint | X issues found`.

---

## Querying the Wiki

When the user asks a question that the wiki might answer:

1. Read `index.md` to find relevant pages by summary.
2. Read the 1-3 most relevant files.
3. Synthesize an answer and cite the source file paths.
