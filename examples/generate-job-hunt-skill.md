# Generate your own job-hunt skill

This tracker is most useful when something *fills it for you*. This is a
fill-in-the-blanks prompt you give to **Claude** to build your own personal
job-hunt skill: it searches the job boards you choose, scores roles against your
criteria, drafts a tailored CV for each promising match, and logs new roles
straight into this tracker's database.

The skill is yours and stays on your machine — your profile and search criteria
never go into this repo.

> ℹ️ **This produces a Claude skill, not Python you run directly.** You hand the
> prompt to Claude; Claude builds a reusable skill you then trigger with
> *"run my job hunt"*.

## Requirements

- **Claude with skill creation** — run this in an environment where Claude can
  create skills and browse the web (e.g. Claude's Cowork mode, which has the
  `skill-creator` skill and a `web_fetch` tool). Plain chat without tools can't
  build or run it.
- **The "Claude in Chrome" browser extension** — **required.** Several boards
  (LinkedIn especially, sometimes Jobserve) are JavaScript-rendered and return an
  empty shell to a normal fetch; the skill needs the Chrome extension to read the
  real page. Install it and make sure it's connected before running a hunt.
  Reed/CWJobs often work via plain fetch, but LinkedIn will not.
- **This tracker set up** — so the roles the skill finds land somewhere useful
  (see “After Claude builds it”).
- **A local folder Claude can write to** — for the drafted CVs and the database.

## How to use it

1. Copy the prompt below.
2. Replace every `<PLACEHOLDER>` with your own details. The more specific you are
   about your background and criteria, the better the scoring and CVs.
3. Paste it to Claude in a session that has skill creation + browsing.
4. Let Claude build the skill, then say **"run my job hunt"** to use it.

---

## The prompt

```text
Using the skill-creator, build me a reusable skill called "job-hunt" that
automates my job search and logs results into my job application tracker
(a local SQLite database). Save my profile and criteria into the skill's
reference files so I don't have to repeat them, and make it re-runnable.

Trigger it when I say "run my job hunt", "find me new roles", or "check for new
jobs". When triggered, it should:

1. CROSS-REFERENCE MY TRACKER FIRST
   Open my tracker database at <PATH TO jobs.db> and read existing roles so you
   never re-process one I've already seen. Collect the known job-ids (the numeric
   id in each job URL) and the known URLs; skip anything already present.
   If the database or its `jobs` table doesn't exist yet, create it using this
   schema (it must match my tracker app exactly):
     CREATE TABLE IF NOT EXISTS jobs (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       date_found TEXT, title TEXT NOT NULL, company TEXT, type TEXT, rate TEXT,
       location TEXT, posted TEXT, link TEXT, fit_notes TEXT,
       status TEXT NOT NULL DEFAULT 'Found', cv_version TEXT, date_applied TEXT,
       outcome TEXT, source_job_id TEXT,
       created_at TEXT NOT NULL DEFAULT (datetime('now')),
       updated_at TEXT NOT NULL DEFAULT (datetime('now'))
     );
   Open the database in WAL mode so it's safe to write while my tracker app is open.

2. SEARCH MY JOB BOARDS
   Search these boards for roles posted in the last 7 days:
     - <BOARD 1 — e.g. Reed — and one or more search URLs>
     - <BOARD 2 — e.g. CWJobs — search URLs>
     - <BOARD 3 — e.g. LinkedIn — search URLs>
   Try a normal web fetch first. If a page returns an empty JavaScript shell
   (LinkedIn especially), use the Claude in Chrome extension to read the rendered
   page text. For each listing extract: title, company/recruiter, rate or salary,
   location, date posted, and the job URL (including its numeric id).

3. SCORE EACH ROLE AGAINST MY CRITERIA
   My background: <YOUR PROFESSIONAL SUMMARY — current role, seniority, key
   skills, industries, and the kind of role you want>.
   Hard filters (skip the role if any fail):
     - <e.g. rate below £X/day, or salary below £Yk>
     - <e.g. location not London or fully remote>
     - already in my tracker
   Soft preferences (note in the fit notes, don't exclude):
     - <e.g. posted within 7 days; top of my rate band; strong title match;
       target sectors such as ...>
   For each role that passes the hard filters, write a one-line fit note
   (~15 words) that includes which board it came from.

4. FETCH THE JOB DESCRIPTION
   For each passing role, fetch the full description and note 3–5 keywords or
   phrases I should echo in the CV.

5. DRAFT A TAILORED CV
   For each passing role, generate a CV as a python-docx document saved to
   <PATH TO YOUR CVs FOLDER>, named "<NAMING PATTERN — e.g. {My Name} - {Role
   Title}.docx>". Tailoring rules: <CV STRUCTURE / STYLE — sections, tone, what to
   emphasise, colours if any>. Use the job-description keywords to adjust the
   headline, summary and skills order. Never invent experience — only reframe and
   re-emphasise what is genuinely on my CV.

6. LOG NEW ROLES INTO THE TRACKER
   Insert each new role into the `jobs` table at <PATH TO jobs.db> with: date_found
   (today), title, company, type, rate, location, posted, link, fit_notes,
   status = "Found", cv_version (the CV filename you just saved), date_applied
   (leave blank), outcome (leave blank). Also store source_job_id = the numeric id
   parsed from the link. Insert NEW roles only; if a role's source_job_id is
   already in the table, skip it — never overwrite rows, so my own status edits
   are preserved.

7. REPORT
   Finish with a short summary: number of new roles found, CVs drafted, skipped
   (already tracked), skipped (below criteria), and a table of the new roles ready
   for me to review and apply.
```

---

## After Claude builds it

Point the tracker at the database the skill writes to. Two easy options:

- **Simplest — read it directly.** Set `JOBTRACKER_DB` in your `.env` to the same
  path you gave the skill (`<PATH TO jobs.db>`). The app then *is* that database;
  new roles appear when you refresh.
- **Keep them separate — import on demand.** Point the skill at its own database,
  set `JOBTRACKER_IMPORT_DB` to it, and click **⬇️ Import new roles** in the app
  (or run `python import_jobs.py`). New roles are merged in; your edits are never
  clobbered.

See the [README](../README.md#configuration) for these settings.

## Notes & caveats

- **Sandboxed file paths.** If you run the skill in Cowork, it sees your files
  through a mounted path (e.g. `/sessions/<name>/mnt/...`) rather than your real
  home path. Use the path the skill actually sees when filling in the placeholders.
- **Respect each board's terms** and rate-limit your searches; this is for your
  own job hunt, not bulk scraping.
- **Keep it honest.** The CV step should only ever reframe real experience — say
  so in your profile notes, and review every generated CV before sending it.
- **The Chrome extension is the usual failure point.** If LinkedIn comes back
  empty, check the extension is installed and connected, then re-run.
