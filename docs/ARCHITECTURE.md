# Architecture & Decisions

How the Job Application Tracker is put together, what it deliberately does and
doesn't do, and the reasoning behind the key calls. New decisions are added as
short records (ADR style) at the end.

## The app in one paragraph

A local-first, single-user application tracker: a **SQLite** database (`jobs.db`)
holds the roles, and a **Streamlit** UI reads and edits them. Optional importers
feed it from a spreadsheet or an external database. It runs entirely on your
machine — no accounts, no server, no data leaves the computer.

## Capability boundary (read this first)

The **Streamlit app is a standalone local web app.** It can talk to its own
SQLite database and the local filesystem — and not much else. In particular it
**cannot**:

- call MCP connectors (Gmail, Jira, …),
- invoke Claude / Cowork or any LLM,
- reach a remote service without credentials wired in.

Anything that needs those lives in the **agent layer** — Claude in Cowork, the
job-hunt skill, scheduled routines. Those produce data (drafted CVs, rows in a
database) that the app then reads. The app and the automation are deliberately
**decoupled**: the agent writes, the app displays and edits.

This boundary is why several "buttons" in this project are deep-links or
import-from-database steps rather than direct integrations.

---

## Decision records

### ADR-001 — Local-first, single-user (SQLite + Streamlit)

**Context.** A personal job-search tool. Privacy matters; infrastructure is
overhead.
**Decision.** Store everything in one local SQLite file; render with Streamlit;
no auth, no hosting by default.
**Consequences.** Zero setup and full privacy, but no multi-user access control
and a single writer. A shared/hosted instance is possible later (see the
deployment backlog) but is out of scope for the default app.

### ADR-002 — The app is decoupled from the agent/connector layer

**Context.** Useful capabilities (search job boards, read Gmail, write Jira,
draft CVs/cover letters with an LLM) require MCP connectors or an LLM. A local
Streamlit process can reach none of these.
**Decision.** Keep the app to local data + UI. Capabilities that need an agent
run in Cowork / the job-hunt skill / scheduled routines and hand results to the
app via the database or files. In-app "buttons" for agent-side capabilities are
either (a) deep-links that open the relevant tool, or (b) imports of data an
agent produced.
**Consequences.** An honest, low-coupling design that works offline; the
trade-off is that "live" agent actions are triggered by asking Claude (or by a
schedule), not by a web button.

### ADR-003 — Gmail integration is minimal and outbound-focused

**Context.** Gmail can in principle tell us about application responses. But for
the way this tracker is actually used:

- genuine recruiter interest arrives **by phone first**, with email only as a
  follow-up — so an "you got a response" alert reports something already known;
- **rejections are not of interest**;
- the thing that matters is **knowing applications are going out** — it's a
  numbers game.

**Decision.**

- Keep a lightweight **"Search Gmail for replies"** deep-link in the app (it opens
  a pre-built Gmail search; it reads nothing and changes nothing).
- **Do not** build automated inbox *response*-reading into the app or a routine —
  low return for this workflow.
- If Gmail is ever automated, point it at the **outbound** side: confirming an
  application actually sent and auto-stamping `Applied` + date, which keeps the
  throughput metrics honest without manual entry.

**Consequences.** We avoid building an OAuth/response-parsing feature that would
mostly surface noise or already-known news. On-demand inbox scanning is still
available by simply asking Claude in Cowork (which has the Gmail connector). The
app's value stays centred on the **apply-and-track loop**, not response-chasing.

### ADR-004 — Status-driven pipeline with a derived "To action" queue

**Context.** The core job is tracking each role through a pipeline.
**Decision.** A single `status` field drives everything. The **To action** view
is *derived* (roles whose status isn't yet actioned), not a separate list — a
role leaves it automatically when its status changes. Closed or
not-to-be-actioned statuses (`Pass`, `Rejected`, `Expired`, …) drop a role out of
the queue.
**Consequences.** No manual "move between lists"; the queue and the metrics stay
consistent with status by construction.

### ADR-005 — De-duplicate on a stable job-id; importers feed the database

**Context.** The same role can be seen more than once, and an external automation
(the job-hunt skill, which runs sandboxed) produces roles the app must absorb
without duplicating.
**Decision.** Parse the numeric job-id from each link as the dedupe key (title +
company as a fallback). External tools write their own SQLite database;
`import_jobs.py` merges new rows into the canonical database and never overwrites
edits made in the app.
**Consequences.** Re-running searches and imports is safe and idempotent; the
canonical tracker stays authoritative.

### ADR-006 — SQLite in WAL mode; configuration via environment

**Context.** A script may write while the app is open, and paths differ per
machine.
**Decision.** Open the database in WAL mode with a busy-timeout (concurrent reads
+ a serialized write, no whole-file lock); read all machine-specific paths from
environment variables (optionally a git-ignored `.env`).
**Consequences.** Safe concurrent use, and a portable, shareable repo with
nothing machine-specific committed.

---

### ADR-007 — Draft CVs on demand, not during the sweep

**Context.** Generating a tailored CV for *every* role a job-hunt sweep turns up
is the most expensive step, and most of those roles are never applied to.
**Decision.** The sweep logs roles as `Found` only — no CVs. CV (and cover-letter)
drafting is triggered **per role, on demand**, by setting its status to
`Draft CV` or `Draft CV & Cover Letter` in the To-action queue; on save the app
generates the document(s), records the filenames, and settles the role to
`CV Drafted`. The in-app draft is a fast, **sector-aware** first cut: a rule-based
engine (`cv_builder.detect_sector`) reads the role's title/fit-notes and picks a
sector-appropriate profile paragraph and competency order (FS / AI / public /
default) — no LLM. Deep JD-tailoring on the few roles actually submitted stays an
agent task (ask Claude). The CV builder reads a **git-ignored `profile.json`**
(the single profile source for the app) so the shareable repo carries no personal
data.
**Consequences.** Effort is spent only on roles the user chooses to pursue;
the job-hunt skill was updated to stop auto-drafting in the sweep.

---

### ADR-008 — Two CVs (screening vs interview); the screening CV is JD-driven via an agent queue

**Context.** The first hurdle is automated screening — keyword/semantic matching of
the CV against the job description — and recruiters later search the ATS by exact
terms. A CV that reads well to a human and a CV that parses well for a machine have
*opposite* requirements: design (columns, tables, graphics) helps the human but
breaks ATS parsers.
**Decision.** Split the document in two.

- **Screening CV** — optimised to pass screening. Plain, single-column, standard
  headings, real text, **no tables/graphics** (`screening_cv.py`). Its content is
  **driven by the specific JD**: the advert's terminology is mirrored against the
  candidate's *genuine* experience, and `keyword_coverage()` reports real gaps. The
  honesty rule is absolute — only keywords for skills the candidate actually has;
  no invented terms (they get caught and collapse at interview). The user always
  reviews before sending.
- **Interview CV** — the polished, human-facing document (design/layout). Out of
  scope for now; this is where any "good-looking" work belongs.

**Delivery — agent queue (not an in-app button).** Reading a JD and authoring the
CV needs an LLM, which the app does not have (ADR-002). So setting a role to
`Draft CV` in the app is a **queue marker only** — it writes nothing. Claude
processes the queue (`screening_queue.list_queue`): reads each JD, writes the
screening CV, then `screening_queue.record_result` files the filename + coverage
back onto the role and settles it to `CV Drafted`.
**Consequences.** Keyword optimisation lives where the JD and the LLM are (the
agent), the app stays a pure local viewer/editor, and the offline sector-aware cut
(ADR-007) remains available as a no-JD fallback. The trade-off is that drafting is
*asynchronous* — it happens when Claude next runs, not on click.

---

### ADR-009 — Interview CV: a designed HTML→PDF, built in-house

**Context.** ADR-008 split the CV into a plain screening CV and a designed
"interview" CV for human readers, but deferred building the latter. Recruiters
increasingly AI-screen even the CVs sent directly to them, so the interview CV must
look polished **and** preserve keyword coverage.
**Decision.** Build it in-house (`interview_cv.py`): render a self-contained,
print-styled HTML and convert to PDF via the locally-installed **headless Chrome**
(`--headless --print-to-pdf`) — no pip/system dependencies, and nothing leaves the
machine. It renders the **same keyword-optimised `screening` payload** as
`screening_cv`, so the designed PDF carries identical AI-screening coverage
(verified with `keyword_coverage`); with no payload it falls back to the
sector-aware profile (ADR-007). Each role therefore has a plain `.docx` (pure-ATS
stage) **and** a designed `.pdf` (human / AI-screened recruiter stage).
**Considered and rejected — external builders (Manus, Lovable).** Manus is an MCP
*client* (can't be called to generate anything). Lovable exposes a server but
builds React *web apps* (a hosted URL, not a document), is OAuth-only (can't be
connected from a non-interactive session) and is gated behind a paid plan — so
neither is automatable here, and both would send personal data off-machine.
**Consequences.** Styling is free, private, repeatable and honest (same content,
just laid out well); the two-format output keeps ATS parsing clean while giving
humans a polished PDF. Requires Chrome/Chromium installed for the PDF export.

---

### ADR-010 — Follow-up emails: verified contacts, a 2-working-day queue, drafts only

**Context.** Applications go quiet; a short, well-timed nudge moves them forward.
But an automated nudger can embarrass (chasing a role that already replied or
rejected) or overstep (sending mail on the user's behalf).
**Decision.** Three cooperating parts, same app/agent split as ADR-008:

- **Contact resolver** (`contact_queue.py`). A follow-up needs a real recipient.
  Live roles without one surface in a *Needs a contact* queue; the agent resolves
  a **verified address only** — the user's Gmail (named sender) → LinkedIn/team
  page (verified named) → company site (monitored generic inbox) — recorded with
  its provenance in `contact_source`. **Never a constructed
  `first.last@domain` guess**; roles with no reachable address are marked
  `none` ("nudge via platform") rather than emailed speculatively.
- **Due queue** (`followup_queue.py`, the single source of the rule). A role is
  due once **2 working days** have passed since `date_applied`. The app section
  lists due roles with an **opt-out tick** (everything starts ticked;
  `follow_up`: 0 default / 1 ticked / 2 opted out).
- **Draft-only delivery.** The agent sweeps Gmail *first* — a reply beats a
  nudge (rejections flip status instead of getting mail). For the rest it writes
  a short, context/age-aware **Gmail draft** (`record_draft` files the link as
  `follow_up_draft`, status `Draft ready`). **The agent never sends.** The user
  reviews, edits and sends in Gmail, then `mark_sent` settles the row
  (`Sent <date>`), which drops it from the queue.

**Consequences.** Follow-ups are timely, personal and safe: every recipient is a
verified address, every email is human-reviewed and human-sent, and inbox
reality always overrides the clock. The trade-off is a two-step loop (queue →
ask Claude) instead of a send button — deliberate, per ADR-002 and the user's
human-in-the-loop preference.

---

### ADR-011 — Optional shared deployment: Postgres, schema-per-user, shared password

**Context.** ADR-001 chose local-first/single-user for privacy and zero setup.
That still holds as the default, but the user also wants to run one hosted
instance (Render) so he and his wife can each use the tracker from anywhere,
with fully separate roles — not a shared board. Render's free web services
have ephemeral local disk, so the SQLite file used locally can't survive a
restart/redeploy there.

**Decision.**

- **Storage.** Add an optional Postgres backend to `db.py`, selected purely by
  the presence of `DATABASE_URL` — unset (the default), the app is byte-for-
  byte the same local SQLite app as before. A `_PgConnAdapter` translates `?`
  placeholders to `%s` and matches the `sqlite3.Connection` surface
  (`.execute()`, dict-like rows via `RealDictCursor`) so every existing query
  in `db.py`, `app.py` and the three agent-queue modules works completely
  unmodified either way.
- **Per-user separation: Postgres schema, not an `owner` column.** Each
  person's data lives in its own Postgres *schema* (`vijay`, `radha`), set via
  `SET search_path` right after connecting. Every unqualified `jobs` query then
  transparently resolves to the right person's table. Rejected: an `owner`
  column with a `WHERE owner = ?` filter threaded through every query and every
  agent-queue function — more invasive, and one missed filter anywhere leaks
  one person's applications into the other's view. Also rejected: a fully
  separate Postgres *database* per person — Render bills per database
  instance, so this would double hosting cost for no isolation benefit over
  schemas.
- **Auth: one shared password, not individual accounts.** A single
  `APP_PASSWORD` gates the app; once through, an `APP_USERS` picker
  (`Vijay:vijay,Radha:radha`) sets the session's active schema/profile. This
  was an explicit choice over per-person logins — the two users trust each
  other completely, so the picker only needs to keep the *data* separate, not
  defend against the other person impersonating you.
- **Per-user CVs.** `profile.<slug>.json` and `cvs/<slug>/` /
  `cover_letters/<slug>/` output folders, resolved by `config.profile_path_for`
  / `cv_dir_for` / `cover_letter_dir_for`. The CV/cover-letter generators
  already accepted optional path overrides (ADR-007/008/009), so no changes
  were needed there — only the callers pass the per-user path.
- **The in-app cover-letter button needed a download button it never had.**
  Every other document-producing workflow (screening CV, interview CV) is
  agent-side (ADR-002/008/009) — Claude runs locally on each person's own
  machine and writes the file to their own disk, so they already have it. The
  one exception is the "✍️ Generate cover letter" button, which runs *inside*
  the Streamlit process itself. Locally that was fine (the user's own
  filesystem); hosted on Render, the user has no way to reach the container's
  disk at all, and Render doesn't guarantee that disk survives anyway — so
  this button now also offers the generated file straight back as a
  `st.download_button`.

**Consequences.** Local single-user setup is completely unaffected — this is
all opt-in behind `DATABASE_URL`/`APP_PASSWORD`/`APP_USERS`. The hosted path
trades a small amount of complexity in `db.py` (a connection adapter, two DDL
dialects) for reusing 100% of the existing query and agent-queue logic
unchanged. See [docs/DEPLOY_RENDER.md](DEPLOY_RENDER.md) for the deploy steps.

---

### ADR-012 — Cover letters: offline default, JD-tailored via the same CV queue

**Context.** `cover_letter.py`'s offline draft (seeded from the profile since
a later fix — no more empty brackets) is still generic: it can't mirror a
specific job description's language or choose which achievements to lead
with, because that's a language-understanding task and the app has no LLM
(ADR-002). "Draft CV & Cover Letter" already existed as a status distinct
from "Draft CV", but nothing acted on the "& Cover Letter" part — it queued
the same screening CV and produced no letter at all.

**Decision.** No new queue module. When Claude processes the existing
screening-CV queue (`screening_queue.list_queue`, ADR-008) and finds a role
whose status is exactly **Draft CV & Cover Letter**, it also reads the JD and
writes 1-2 tailored body paragraphs in the same pass — mirroring the JD's
language against the candidate's *genuine* experience, the same honesty rule
as the screening CV (no invented claims) — then calls
`cover_letter.generate_cover_letter(role, body_paragraphs=[...], profile_path=...,
out_dir=...)`, which slots them straight into the letter in place of the
offline summary, and records the filename with a plain
`db.update_job(conn, role_id, {"cover_letter": filename})` (the same write the
in-app button already does — no dedicated queue/record function needed for
something this simple).

**Rejected: a separate cover-letter queue, filtered independently by
status.** Once `screening_queue.record_result` settles a role to **CV
Drafted**, a second automation filtering on the "...& Cover Letter" status
would never see the role again — whichever of (CV, letter) runs first flips
the status away from the trigger value the other one is watching for. Doing
both in one pass, off one JD read, sidesteps the ordering hazard entirely and
is also just less work (one JD read instead of two).

**Consequences.** The offline in-app button is unchanged (still the
profile-seeded default, no LLM, works with no Claude session at all). JD
quality now matches the screening CV's, for the cost of Claude reading the JD
once instead of twice. If a genuinely large cover-letter-specific feature set
shows up later (e.g. independent re-tailoring without re-running the CV),
revisit as its own queue then.

---

### ADR-013 — Optional in-app AI drafting: direct API call, documents only

**Context.** ADR-012's queue (Draft CV & Cover Letter → ask Claude) works but
is a two-step, two-tool flow: set a status in the app, then separately open
Claude and type a prompt. The user asked whether Claude could be called
directly from the app instead, for a true one-click draft.

**Decision.** Add an optional, separate path — a new **✨ AI-tailored CV &
cover letter** section (`ai_draft.py`) that calls the Anthropic API directly
from the Streamlit process, gated entirely on `ANTHROPIC_API_KEY` being set
(unset, the section doesn't render — everything else is unchanged). The user
pastes the JD text (no attempt to auto-fetch the job URL — many boards block
scraping or require JS rendering; pasting is reliable and keeps scope small),
picks a role, and clicks once. `ai_draft.draft()` sends the JD + the
candidate's real profile to Claude with the same honesty rule as the
screening CV (ADR-008: genuine experience only, never invented), and gets
back a structured payload (Pydantic `output_format`, not free text) shaped to
match exactly what `screening_cv.generate_screening_cv` and
`cover_letter.generate_cover_letter(..., body_paragraphs=...)` already
accept — so this path reuses 100% of the existing document rendering; the
only new code is the API call and payload shape.

**Scope: documents only, not Gmail-dependent workflows.** Contact resolution
and follow-up drafting stay "ask Claude" — bringing those in-app would mean
storing Gmail OAuth tokens for both users in the hosted database, a
meaningfully bigger and more sensitive piece of infrastructure than one API
key (see ADR-002/ADR-003, which kept Gmail out of the app's scope for the
same reason). CV/cover-letter drafting needs only the JD text and the
profile — both already in hand — so it's the one workflow that can move
in-app without that trade-off.

**Cost is explicit and separate.** Unlike "ask Claude" (which rides on
whatever Claude session/subscription the user already has), this bills
per-generation against `ANTHROPIC_API_KEY` — a deliberate, disclosed new
recurring cost the user opted into, not a hidden one.

**Consequences.** Three ways to get a drafted CV/cover letter now coexist:
the fully offline button (no LLM, instant, generic), the agent queue (any
Claude session, free beyond what's already paid for, two steps), and this
one-click path (fastest, but billed separately). All three write the same
kind of output through the same renderers, so none of them is a special case
elsewhere in the app.

---

*Add new decisions as `ADR-NNN` records above this line, newest last.*
