"""Generate a styled "interview" CV — designed HTML rendered to PDF.

Unlike screening_cv (deliberately plain and ATS-safe), this produces a visually
polished, professional PDF for *human* readers — recruiters and hiring managers
at the shortlist/interview stage. It reuses profile.json (real achievements) and
the sector-aware tailoring from cv_builder, renders a self-contained HTML with
print CSS, and converts to PDF via headless Chrome (no extra pip dependencies;
nothing leaves the machine).
"""

from __future__ import annotations

import html
import re
import shutil
import subprocess
from pathlib import Path

import config
from cv_builder import detect_sector, load_profile, resolve_profile

NAVY = "#0d2b55"
TEAL = "#00709e"
INK = "#26272b"
MID = "#52525b"
LIGHT = "#71717a"
LINE = "#e4e7ec"
CHIPBG = "#eef4f7"

_CHROME = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome"),
    shutil.which("chromium"),
    shutil.which("chrome"),
]


def _chrome() -> str:
    for c in _CHROME:
        if c and Path(c).exists():
            return c
    raise RuntimeError("Chrome/Chromium not found — needed to export the PDF.")


def _e(s) -> str:
    return html.escape(str(s or ""))


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]+', "", (name or "")).strip() or "Role"


def render_html(role: dict, profile: dict, screening: dict | None = None) -> str:
    # When a screening payload is supplied, render its keyword-optimised content
    # (so the designed CV still passes recruiter AI screening); otherwise fall
    # back to the sector-aware profile defaults.
    if screening:
        title = (screening.get("target_title") or role.get("title") or "").strip()
        summary = screening.get("summary", "")
        comps = [c for c in (screening.get("core_skills") or []) if str(c).strip()][:12]
        jobs = screening.get("experience") or profile.get("jobs", [])
    else:
        title = (role.get("title") or "").strip()
        sector = detect_sector(role)
        summary, comps = resolve_profile(profile, sector, max_competencies=10)
        jobs = profile.get("jobs", [])

    chips = "".join(f'<span class="chip">{_e(c)}</span>' for c in comps)

    jobs_html = []
    for job in jobs:
        bullets = "".join(f"<li>{_e(b)}</li>" for b in job.get("bullets", []))
        jobs_html.append(f"""
        <div class="job">
          <div class="jobhead">
            <div class="role">{_e(job.get('title'))} <span class="at">·</span>
              <span class="co">{_e(job.get('company'))}</span></div>
            <div class="dates">{_e(job.get('dates'))}</div>
          </div>
          <ul>{bullets}</ul>
        </div>""")
    jobs_block = "".join(jobs_html)

    ach = "".join(f"<li>{_e(a)}</li>" for a in profile.get("achievements", []))
    ach_block = (
        f'<section><h2>Key Achievements</h2><ul class="ach">{ach}</ul></section>' if ach else ""
    )
    rtw = profile.get("rightToWork")
    rtw_block = f'<div class="foot"><b>Right to work:</b> {_e(rtw)}</div>' if rtw else ""

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<style>
  @page {{ size: A4; margin: 13mm 14mm; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; font-family:"Helvetica Neue",Arial,sans-serif; color:{INK};
         font-size:10.3px; line-height:1.45;
         -webkit-print-color-adjust:exact; print-color-adjust:exact; }}
  .name {{ font-size:27px; font-weight:800; letter-spacing:-.3px; color:{NAVY}; margin:0; }}
  .title {{ font-size:12.5px; font-weight:600; color:{TEAL}; margin:2px 0 0; letter-spacing:.2px; }}
  .contact {{ font-size:9.6px; color:{LIGHT}; margin-top:5px; }}
  .rule {{ height:3px; background:linear-gradient(90deg,{NAVY},{TEAL});
           border:0; margin:11px 0 4px; border-radius:2px; }}
  h2 {{ font-size:10px; font-weight:800; letter-spacing:1.4px; text-transform:uppercase;
        color:{NAVY}; margin:15px 0 6px; padding-bottom:3px; border-bottom:1px solid {LINE}; }}
  section {{ margin-top:2px; }}
  p.summary {{ margin:3px 0 0; color:{MID}; }}
  .chips {{ display:flex; flex-wrap:wrap; gap:5px; margin-top:3px; }}
  .chip {{ background:{CHIPBG}; color:{NAVY}; border:1px solid #d7e5ec; border-radius:11px;
          padding:2.5px 9px; font-size:9px; font-weight:600; }}
  .job {{ margin-top:8px; page-break-inside:avoid; }}
  .jobhead {{ display:flex; justify-content:space-between; align-items:baseline; gap:10px; }}
  .role {{ font-size:11px; font-weight:700; color:{NAVY}; }}
  .at {{ color:{LIGHT}; font-weight:400; }}
  .co {{ color:{TEAL}; font-weight:600; font-style:italic; }}
  .dates {{ font-size:9.2px; color:{LIGHT}; white-space:nowrap; }}
  ul {{ margin:4px 0 0; padding-left:15px; }}
  li {{ margin:1.5px 0; color:{MID}; }}
  ul.ach li {{ color:{INK}; }}
  .foot {{ margin-top:13px; color:{MID}; font-size:9.6px; }}
  .foot b {{ color:{NAVY}; }}
</style></head>
<body>
  <div class="name">{_e(profile.get('name'))}</div>
  <div class="title">{_e(title)}</div>
  <div class="contact">{_e(profile.get('contact'))}</div>
  <hr class="rule">

  <section><h2>Profile</h2><p class="summary">{_e(summary)}</p></section>

  <section><h2>Core Competencies</h2><div class="chips">{chips}</div></section>

  <section><h2>Professional Experience</h2>{jobs_block}</section>

  {ach_block}

  <section><h2>Certifications &amp; Education</h2>
    <div class="foot"><b>Certifications:</b> {_e(profile.get('certifications'))}</div>
    <div class="foot"><b>Education:</b> {_e(profile.get('education'))}</div>
    {rtw_block}
  </section>
</body></html>"""


def generate_interview_cv(role: dict, screening: dict | None = None,
                          profile_path=None, out_dir=None) -> Path:
    """Render a designed interview CV for ``role`` and return the saved PDF path.

    If ``screening`` (the same payload used by screening_cv) is supplied, its
    keyword-optimised content is rendered so the designed CV still holds up to
    recruiter AI screening.
    """
    prof = load_profile(profile_path)
    out_dir = Path(out_dir) if out_dir else config.CV_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    target = ((screening or {}).get("target_title") or role.get("title") or "Role").strip()
    stem = f"{prof.get('name', 'CV')} - Interview - {_safe(target)}"
    html_path = out_dir / f"{stem}.html"
    pdf_path = out_dir / f"{stem}.pdf"
    html_path.write_text(render_html(role, prof, screening), encoding="utf-8")
    subprocess.run(
        [_chrome(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf_path}", html_path.as_uri()],
        check=True, capture_output=True, timeout=90,
    )
    return pdf_path
