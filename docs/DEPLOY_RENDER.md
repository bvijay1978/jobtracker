# Deploying to Render (shared, multi-user)

This deploys the tracker as one hosted app that you and Radha both log into
with a shared password, each seeing only your own roles. See
[ARCHITECTURE.md](ARCHITECTURE.md) (ADR-011) for how the separation works.

Local single-user use (`streamlit run app.py` on your own machine) is
completely unaffected by any of this — it's a separate, optional mode gated
behind environment variables that only exist on Render.

## 1. Push to GitHub

The repo already lives at `github.com/bvijay1978/jobtracker` — Render deploys
straight from it, so just make sure your latest commits are pushed.

## 2. Deploy the Blueprint

1. In the Render dashboard: **New → Blueprint**.
2. Connect the `bvijay1978/jobtracker` repo. Render reads
   [`render.yaml`](../render.yaml) and provisions two resources:
   - `jobtracker-db` — a free Postgres instance.
   - `jobtracker` — the web service, wired to it via `DATABASE_URL`.
3. Click **Apply** to create both. The first deploy will fail to *log in*
   (no password set yet) — that's expected, continue to step 3.

## 3. Set the shared password

1. Open the `jobtracker` web service → **Environment**.
2. Add `APP_PASSWORD` with the password you and Radha will both use. It's
   marked `sync: false` in `render.yaml` specifically so it's never committed
   to the repo — you set it once, here, manually.
3. Save — Render redeploys automatically.

## 4. (Optional) Enable one-click AI drafting

The app can call Claude directly to draft a JD-tailored CV and cover letter
in one click (ADR-013) — no separate chat needed. This is optional and has
its own ongoing cost (billed per generation, separate from whatever you
already pay for Claude):

1. Get an API key from [console.anthropic.com](https://console.anthropic.com).
2. Open the `jobtracker` service → **Environment** → add `ANTHROPIC_API_KEY`
   (also `sync: false` — never committed).
3. Save — Render redeploys. The **✨ AI-tailored CV & cover letter** section
   at the bottom of the app now works; without the key, it just shows a note
   pointing at the existing "ask Claude" queue instead.

## 5. First-run smoke test

1. Open the service URL. Free-tier services spin down after 15 minutes idle,
   so the first hit after a while can take 30-60 seconds to wake up — that's
   normal, not a hang.
2. Log in with `APP_PASSWORD`, then pick **Vijay** — the board should be
   empty (a fresh schema). Add a test role, save.
3. Log out (clear the browser's local storage or open an incognito window),
   log back in, pick **Radha** — confirm the board is empty and the test role
   from step 2 does *not* appear.
4. Generate a cover letter for a role and confirm the **⬇️ Download** button
   delivers the file — this is one of two features that run on the server
   itself rather than on your own machine, so it needs the download button to
   be reachable at all (see ADR-011). If you set `ANTHROPIC_API_KEY`, also try
   the **✨ AI-tailored CV & cover letter** section with a pasted job ad.
5. Delete the test role, or leave it — either way, you're set.

## Notes for the agent-side workflows (Claude drafting CVs, resolving
contacts, drafting follow-ups)

These still run wherever you run Claude (per ADR-002 — the app itself only
talks to an LLM directly for the optional one-click drafting above; contact
resolution and follow-up drafting need Gmail, which stays off the server on
purpose), not on Render. To point a local Claude session at the same hosted
data instead of your local `jobs.db`:

1. Set `DATABASE_URL` in your local `.env` (copy it from the Render dashboard
   → `jobtracker-db` → **Connections**) and set `JOBTRACKER_PROFILE` /
   `JOBTRACKER_CV_DIR` / `JOBTRACKER_COVER_LETTER_DIR` to your slug's files
   (e.g. `profile.vijay.json`, `cvs/vijay/`).
2. Any script Claude writes must open the connection with your schema —
   `db.connect(schema="vijay")` — not the bare `db.connect()`. That schema
   argument is what actually selects your data (the env vars above only cover
   the profile/CV side); it's a small, deliberate manual step rather than
   another env var, so it's never ambiguous which person's data a script is
   about to touch.
