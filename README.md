# Apply Copilot

Auto-fill job applications on Handshake (and external ATS forms — Greenhouse,
Lever, Workday, Ashby, generic). Stops before final Submit by default — you
review the filled form and click Submit yourself.

> ⚠️ **Use at your own risk.** Some job platforms prohibit automation in their
> terms of service. This tool is for personal use only. Don't redistribute on
> public GitHub without understanding the legal implications. See `DESIGN.md`
> §5.1 for the risk register.

## What it does

1. **You upload your base resume** (`.docx`) once via the web dashboard.
2. **You fill your profile** (name / email / school / etc.) in the dashboard form.
3. **The autopilot opens Handshake, paginates jobs**, and for each new posting:
   - Scrapes the JD
   - Picks which of your resume directions fits best (LLM)
   - Edits your resume to cover JD keywords *while preserving your format and
     staying ≤ 2 pages*
   - Generates a per-job cover letter
   - Opens the apply modal, uploads files, clicks Submit
4. **Dashboard shows** what was submitted / pending review, with filters by
   employment type, status, etc.

## Requirements

- **Python 3.11+** ([download](https://www.python.org/downloads/))
- **A modern browser will be downloaded automatically** by Playwright (~500 MB,
  one-time)
- **OpenAI API key** ([get one](https://platform.openai.com/api-keys)) — funds
  cost about $0.10–0.30 per fully-prepped application
- **A Handshake account** — you log in once manually inside the bundled browser
- **Your base resume in `.docx`** (you upload it via the dashboard)

Works on **macOS, Windows, and Linux**.

## Install

### macOS / Linux

```bash
git clone https://github.com/your/apply-copilot.git
cd apply-copilot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### Windows (PowerShell)

```powershell
git clone https://github.com/your/apply-copilot.git
cd apply-copilot
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

## Setup

Set your OpenAI API key (one-time):

**macOS / Linux**: add to `~/.zshrc` or `~/.bashrc`:
```bash
export OPENAI_API_KEY="sk-..."
```

**Windows**: System Properties → Environment Variables → New →
`OPENAI_API_KEY = sk-...`

## Run

```bash
python -m apply_copilot                       # dashboard at http://localhost:8989
```

Then open <http://localhost:8989> and follow the steps below. **Do them in
order** — the first-time Handshake login (step 4) is the only manual
authentication you'll need; subsequent runs reuse that session.

### 1. Profile tab
Fill in name, email, phone, school, GPA, work-auth, etc. Hit **Save**. The
profile is stored locally in `~/.apply_copilot/profile.json` — nothing leaves
your machine until the autopilot uses it for cover letters / form fills.

### 2. Resumes tab
Upload one or more base resumes in `.docx`. Each upload has a *direction*
label (e.g. `mle`, `sde_general`, `agent`, or `default`). When the autopilot
sees a job, an LLM picks the best-fit direction; the system falls back to
your **default** resume if no specific match is uploaded.

> ⚠️ Resume edits only run on `.docx`. PDF-only uploads work for upload-as-is
> but the system can't add JD keywords to them.

### 3. Autopilot tab — *first run only*
Pick:
- **Platform**: Handshake (more coming)
- **Employment type**: Intern or Full-time
- **Sort**: Newest is usually best; Most-relevant is Handshake's default but
  changes daily
- **Max jobs**: 50 is a sensible first run
- **External mode**: `skip` (don't open external ATS pages) is the safest
  default. Use `fill` if you want the system to auto-fill external forms and
  leave them open for you to review and submit manually.

Click **Start**. A Chromium window pops up.

### 4. First-time Handshake login (one-time)
The bundled Chromium opens on `https://app.joinhandshake.com/job-search`.

**You'll see Handshake's login wall** — that's normal, the autopilot can't
fake SSO. Do this **once**:

1. Click your school's SSO login button
2. Authenticate with your school credentials (Duo / 2FA / etc.)
3. Get to the actual job search page — confirm you see jobs listed
4. **Don't close the window.** The autopilot starts scraping as soon as it
   detects you're logged in.

The session is persisted to `~/.apply_copilot/browser/` so future runs
auto-login (until Handshake's cookie expires, usually 2-4 weeks).

> 💡 If autopilot starts before you finish logging in, it'll fail the JD
> scrape step and skip jobs. Stop it from the dashboard, finish logging in,
> then click Start again.

### 5. Subsequent runs
After the first login, the entire flow is hands-off:
- Click **Start** in the Autopilot tab
- Watch logs stream in the dashboard
- Or close the dashboard tab and walk away — the autopilot runs in the background

### 6. Review submissions
Open the **Applications tab**. Filter by status:
- ✅ **Submitted** — fully prepped and submitted on Handshake
- 📝 **External filled** — auto-filled an external ATS page; **you still need
  to click Submit** on that tab (it stays open)
- 🔌 **External pending** — was external-only and `external_mode=skip` was set
- ⛔ **Gate failed** — JD coverage was too low to auto-submit. Click into it
  and decide manually.
- ⏭ **Skipped (eligibility)** — ineligible (citizen-only / GC-only / etc.)
- ⏭ **Skipped (picker)** — LLM determined no resume direction fits

## Costs

OpenAI API:
- Pre-flight skip (external apply / ineligible JD): $0
- LLM picker only: $0.001
- Full prep + submit: $0.06–0.11 / job
- Typical: $3–6 per 50 applications

## Stopping / resuming

The autopilot can be stopped at any time from the dashboard or with Ctrl+C in
the terminal. Resume picks up where it left off (skips URLs already in the
submitted log + locally-processed bundles on disk).

## How resume editing works

When the system adds JD keywords to your resume, it:

- **Only edits your uploaded `.docx`** (preserves your font, style, layout)
- **Only adds words** (never deletes your existing content)
- **Bolds only the added phrases** (so it's obvious what changed)
- **Re-renders to PDF and checks the page count** — if the edit pushes it past
  2 pages, the edit is reverted
- **Final output**: a PDF that looks like yours but covers the JD better

If the system can't safely edit your resume to cover the JD (e.g. the JD wants
"Rust" but you've never used Rust), the job is left in `Prepped` state and
flagged for your manual review on the dashboard.

## Privacy

Everything is **stored locally on your machine**:

- Profile: `~/.apply_copilot/profile.json`
- Uploaded resumes: `~/.apply_copilot/resumes/`
- Submission history: `~/.apply_copilot/submissions.db` (SQLite)
- Browser session: `~/.apply_copilot/browser/`

The only data sent over the network is:
- JD text + your profile → OpenAI API (for resume edits, cover letters)
- Your application data → the job site you're applying to

No analytics. No telemetry. Delete the `~/.apply_copilot/` folder to nuke
everything.

## Resume format

Apply Copilot's editor and translator expect a structured `.docx` with
predictable section anchors (EDUCATION → INTERNSHIP → TECHNICAL SKILLS →
PROJECT EXPERIENCES). See [`examples/templates/`](./examples/templates/) for
a reference English resume + (optional) translated Chinese counterpart and a
full description of the expected anchors / constraints.

## License

[Choose: MIT? Apache 2.0? Or "Source Available — Personal Use Only"]

## Limitations

- Workday multi-step wizard: ~50% success rate. Many require manual completion.
- Some ATSes (iCIMS legacy, Taleo) aren't yet supported.
- Resume edits are LLM-generated — they're competent but not perfect. Review
  before submitting (the system stops before Submit by default).
- Mass auto-applying can flag your account on some platforms. Use sensibly.

## Troubleshooting

**"OPENAI_API_KEY not set" in the dashboard banner**
You exported the key in a new shell, then ran `python -m apply_copilot` in a
different shell that doesn't see it. Either export it again in the same shell,
or set it permanently in `~/.zshrc` / `~/.bashrc` (mac) / System Properties
→ Environment Variables (Windows).

**Autopilot click does nothing**
Check the **Status** field at the top of the Autopilot tab. If it says
`▶ running pid=...`, scroll the log pane — Playwright is starting Chromium
(~5 s on first run while it copies the profile).

**Chromium window closes immediately**
Almost always means the persistent browser profile is corrupted (e.g. from a
kill -9 during a previous run). Delete `~/.apply_copilot/browser/` and run
again — you'll need to log in to Handshake one more time.

**"要恢复页面 / Restore pages?" dialog every launch**
The previous run didn't exit cleanly. Click "X" or press Esc — the autopilot
will continue. To prevent it permanently: stop the autopilot from the
dashboard (not Ctrl+C) so the browser closes gracefully.

**`docx2pdf` fails on Windows / mac without Office**
The system tries Word → LibreOffice → `soffice` in order. Install
[LibreOffice](https://www.libreoffice.org/download/) (free) if you don't have
Word — the autopilot will pick it up automatically.

**Submissions don't show up in the dashboard**
Refresh the Applications tab. The autopilot writes to SQLite on each event
but the dashboard polls only when you load that tab.

**Want to reset everything**
Delete `~/.apply_copilot/`. You'll lose all submission history, uploaded
resumes, browser session, and QA memory — but the system reinitializes
cleanly on next launch.
