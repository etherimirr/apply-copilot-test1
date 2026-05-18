# Resume templates

Reference resumes that demonstrate the format Apply Copilot's resume editor /
translator / autopilot pipeline expects. Use these as a starting point —
upload your own version via the **Resumes** tab in the dashboard, then run
the **Resume Editor** to translate or apply targeted edits.

## Files

| File | Lang | Purpose |
|---|---|---|
| `resume_en.docx` | English | Reference template for the structure expected by `resume_editor.py` (skill_add anchors, bullet anchors, page layout). |
| `resume_zh.docx` | 简体中文 | Generated from `resume_en.docx` via `apply_copilot.core.translator`. Demonstrates run-level preservation of tech terms during translation. |

> If `resume_zh.docx` is missing, generate it yourself:
> ```bash
> OPENAI_API_KEY="sk-..." python3 -c "
> from apply_copilot.core import resume_editor, translator
> doc = resume_editor.load_docx('examples/templates/resume_en.docx')
> translator.translate_docx(doc, target_lang='zh', source_lang='en')
> resume_editor.save_docx(doc, 'examples/templates/resume_zh.docx')
> "
> ```
> Or via the dashboard: upload `resume_en.docx` → switch to **Resume Editor**
> tab → click **Translate → 中文** → the new resume is saved into your
> `~/.apply_copilot/resumes/` directory and shown in the list.

## Expected structure

The editor's anchoring logic (used by `skills_add` and `bullet_inject`) relies
on a predictable section order. Follow this skeleton:

```
NAME (h0)
Contact line: city, phone, email, LinkedIn, GitHub

EDUCATION (h1, ALL-CAPS section header)
  School name [TAB] location
  Degree, GPA [TAB] graduation date
  Coursework: ...

INTERNSHIP / EXPERIENCE (h1)
  Company name [TAB] location
  Title [TAB] dates
  • Bullet (action verb + concrete result + tech)
  • Bullet
  • Bullet

TECHNICAL SKILLS (h1)
  Programming Languages: Python, Java, ...
  ML Frameworks & Libraries: PyTorch, TensorFlow, ...
  ML Systems: ...
  Backend & Infrastructure: ...
  Tools & Workflow: ...

PROJECT EXPERIENCES (h1)
  Project name [TAB] dates
  • Bullet describing architecture / outcome
  • Bullet
```

Key constraints (enforced by `resume_editor.py`):

1. **Single source `.docx`** — the editor parses python-docx paragraphs.
   PDF-only resumes can't be edited (only uploaded as-is).
2. **Anchored Skills lines** — `skills_add(category, keywords)` looks for a
   paragraph whose **first colon-prefixed label** matches `category` (case-
   insensitive substring). The keywords are appended after a comma, bolded.
3. **Anchored Bullets** — `bullet_inject(anchor, addition)` matches any
   paragraph whose text **starts with** `anchor` (first 30 chars, case-
   insensitive). The addition is appended (bolded) at the end of that bullet.
4. **Page limit** — every edit is followed by a docx → PDF render. If the
   page count exceeds `MAX_RESUME_PAGES` (default 2), the edit is reverted.
5. **No new sections** — the editor cannot create new headings or sections.
   Make sure every skill category and bullet anchor you'd want to inject into
   already exists in the base resume.

## What the translator preserves

`translator.translate_docx()` is run-aware — bold spans, hyperlinks, tables,
and paragraph styles survive a translation pass. The LLM is given an explicit
keep-token glossary so the following never get translated:

- Tech terms (`Python`, `PyTorch`, `LoRA`, `Docker`, `AWS`, `LLM`, ...)
- URLs, emails, phone numbers
- Numerical metrics (`40K`, `99.9%`, `60%`), GPA values
- Year ranges (`2024-2026`), month-year dates (`Jul 2025`)
- Proper nouns (Columbia University, Johnson & Johnson, ...)

Everything else around those tokens is translated naturally — bullets stay
action-led, headings stay terse.

## Want to contribute a different template?

Open a PR with:
- `examples/templates/resume_<role>.docx`
- 1-2 sentences describing the role / direction in this README
- (optional) `resume_<role>_zh.docx` for the translated counterpart
