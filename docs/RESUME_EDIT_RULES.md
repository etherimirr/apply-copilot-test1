# Resume edit rules

The system edits your uploaded `.docx` resume to cover JD keywords for each
application. These rules are the hard contract — the editor enforces them
in code and won't ship a resume that violates them.

## Hard rules (no exceptions)

### Format preservation
1. **Read user-uploaded `.docx`, edit in place.** Don't replace fonts,
   paragraph styles, headers/footers, or section dividers.
2. **No section reordering.** Edits target existing paragraphs only.
3. **No new sections.** If the JD asks for something not present in any
   uploaded resume direction, the system marks the JD as `gate_fail` rather
   than fabricating a section.
4. **Existing bold spans are preserved.** Bold can only be ADDED (to mark
   keyword injections), never removed.
5. **Page limit enforced.** After every edit, the docx is rendered to PDF
   and page-counted. If page count exceeds `MAX_RESUME_PAGES` (default 2),
   the edit is reverted via element-tree rollback.

### Edits allowed
1. **`skills_add`** — append keywords to an existing skills category line
   (e.g. `Programming Languages: Python, Java, **Go**, **Rust**`). Never
   invent a new category. Never delete existing skills.
2. **`bullet_inject`** — append a phrase to an existing bullet whose text
   starts with the anchor. The addition is bolded.
3. **No deletions, ever.** The editor cannot drop existing bullets,
   projects, internships, or skills.

### Edits FORBIDDEN
- Fabricated metrics ("thousands of items", "10x improvement") not grounded
  in your project_kb or original resume text.
- New section headers.
- Removing existing content.
- Changing typography (font, size, paragraph style) outside the bold-add rule.

## Coverage scoring

The audit extracts every technical keyword from the JD (typically 15-30 per
posting), then classifies each as:
- `explicit`: appears verbatim (or close synonym) in resume
- `implicit`: resume describes work that semantically covers it
- `missing`: not covered; *may* be addressed via `skills_add` /
  `bullet_inject`
- `no_fix`: missing and cannot be reasonably added (e.g. JD wants "Solana
  smart contracts" and your resume has no blockchain work)

Two coverage percentages are computed:
- **Raw coverage** = (explicit + implicit) / total
- **Addressable coverage** = (explicit + implicit) / (total - no_fix)

A safety floor catches a coverage-gaming bug: if raw < 30% but addressable
> 80% (LLM marked too many keywords as no_fix), we trust the raw number.
See `apply_copilot/core/audit.py::_compute_addressable_coverage`.

## Auto-submit gate

Default `AUTO_SUBMIT_MIN_COVERAGE` is 70%. If the edited resume's
addressable coverage is below this, the submission is recorded as
`gate_fail` and you review it manually in the Applications tab.

## HARD-FORBIDDEN content (cover letter + resume + open answers)

Recruiter-facing content must read like a senior engineer's portfolio, NOT
a student's annotated work log. The `cl_writer.critic_check()` rejects any
draft containing:

1. **Git refs** — `<org>/<repo>#<num>`, `PR #N`, `pull request`, `branch
   <name>`, `feat/`, commit hashes, GitHub URL fragments
2. **Coursework codes** — `E6792`, `E4750`, `Lab N`, `Assignment N`, "for
   my class", "during my coursework", "class project"
3. **Process annotations** — "Collaborating on...", "working through the
   ...", "in this PR", "via the branch", "as part of my homework"
4. **Internal dev artifacts** — staging URLs, file dumps, bearer-token
   paths, internal directory references
5. **AI-cliche words** — "leverage", "transformative", "cutting-edge",
   "passionate", "synergy", "delve into"
6. **Em / en dashes** — use periods or commas instead

**Write instead:**
- Architecture decisions: "Designed a 4-stage pipeline (planner → executor
  → verifier → critic)"
- Technical tradeoffs: "Chose FAISS over Pinecone for sub-50ms latency on
  100K vectors"
- Concrete results: "Reduced manual review time 60%; achieved 23% benchmark
  improvement"
- Domain match tied to JD: "Designed evaluation framework for healthcare-
  grade conversational agents"

## How the editor decides what to add

For each `missing` keyword the audit LLM suggests one of:
- `skills_add:<category>:<keyword>` — append to existing skills line
- `bullet_inject:<anchor>:<keyword>` — append to bullet starting with anchor
- `project_swap:<project_id>` — would swap in a different project (NOT
  currently applied automatically; flagged for user review)

The first up to 8 fixes are attempted. Each is applied, the page count is
checked, and if exceeded the edit is rolled back. The final state is
re-audited so the dashboard shows the *actual* coverage shipped, not the
pre-edit number.

## What if the editor can't safely match the JD?

If the addressable coverage stays below the auto-submit threshold after all
allowable edits, the submission is recorded with status `gate_fail`. The
generated resume and CL stay in `~/.apply_copilot/generated/` so you can
review and submit manually.
