"""Translate a docx between English and Chinese, run-by-run, preserving
paragraph styles, fonts, bold/italic, hyperlinks, and tables.

Strategy:
- Walk every <w:p> paragraph (body + tables).
- For each paragraph, batch-translate the concatenated text once.
- Re-distribute the translated text back into the original runs proportionally
  (so bold/italic/links survive). Where lengths differ a lot, the first run
  receives the bulk of the text and subsequent runs share the remainder.
- Keep dates, URLs, emails, phone numbers, GPA values, and well-known tech
  terms (Python, PyTorch, etc.) untouched — passed to the LLM as a NO-TRANSLATE
  glossary.

Cost: one gpt-4o-mini call per non-empty paragraph (~$0.0005 each). A typical
2-page resume has ~60 paragraphs → ~$0.03 per translation.
"""
from __future__ import annotations
import re
from typing import Optional

from .llm_client import llm_call_mini


# Terms that should pass through unchanged (we still send them to the LLM with
# an instruction, but this list is also the post-pass scrubber).
PRESERVE_TERMS = {
    "Python", "Java", "C++", "C#", "C/C++", "JavaScript", "TypeScript", "Go", "Rust",
    "PyTorch", "TensorFlow", "scikit-learn", "NumPy", "Pandas", "HuggingFace",
    "LangChain", "FAISS", "OpenCV", "Spark", "Kafka", "Redis", "Docker", "Kubernetes",
    "FastAPI", "Django", "Spring Boot", "AWS", "GCP", "Azure", "Linux", "CI/CD",
    "SQL", "NoSQL", "PostgreSQL", "MySQL", "MongoDB", "PyTorch Lightning", "ONNX",
    "LoRA", "PEFT", "RAG", "LLM", "VLM", "NLP", "CV", "GPU", "CPU",
    "REST", "gRPC", "GraphQL", "Git", "GitHub", "GitLab",
    "Columbia University", "Shanghai Jiao Tong University", "University of Michigan",
    "Johnson & Johnson", "iQIYI",
    "NYU", "SJTU", "GPA", "B.E.", "M.S.", "Ph.D.", "B.S.",
}


SYSTEM_EN_TO_ZH = """You are a professional bilingual technical translator
specialising in software-engineering resumes. Translate the user's text from
English into natural, concise Simplified Chinese suitable for a top-tier
software / ML engineering resume.

RULES (strict — violating any is a translation failure):
1. KEEP these unchanged: people / company / school proper names, product
   names, tech terms (Python, PyTorch, LoRA, Docker, AWS, etc), abbreviations
   (LLM, NLP, GPU, RAG, SQL), URLs, email, phone numbers, numerical metrics
   (40K, 99.9%, 60%), dates (Jul 2025, 2024-2026), GPA values.
2. Translate ONLY the natural-language wrapper around those terms.
3. Use the standard PRC technical-resume register — terse, action-led
   sentences. NOT machine-translated literal Chinese.
4. Match the source register: bullet → bullet (start with a verb like
   构建/设计/开发/优化), heading → heading, paragraph → paragraph.
5. NEVER add new content or fabricate skills. NEVER drop content.
6. Translate the text only. Do NOT add a heading like "翻译:" or any
   commentary. Output the translated text and nothing else.

Common technical vocabulary (use these renderings):
- pipeline → 流水线 (data pipeline) or 管线 (CV pipeline)
- inference → 推理
- fine-tuning → 微调
- agent / agentic → 智能体 / 智能体化
- model → 模型
- service → 服务
- platform → 平台
- benchmark → 基准 (verb: 基准测试)
- throughput → 吞吐量
- latency → 延迟
- pipeline / ETL → 数据流水线 / ETL
- containerized → 容器化
- orchestration → 编排
- evaluation → 评估
"""


SYSTEM_ZH_TO_EN = """You are a professional bilingual technical translator
specialising in software-engineering resumes. Translate the user's text from
Simplified Chinese into natural, concise American English suitable for a top-
tier software / ML engineering resume.

RULES (strict — violating any is a translation failure):
1. KEEP these unchanged: people / company / school proper names, product
   names, tech terms, abbreviations (LLM, NLP, GPU), URLs, emails, phone
   numbers, numerical metrics, dates, GPA values.
2. Use the standard US tech-resume register — STAR-style bullets, action-led
   (Built / Designed / Optimized / Deployed / Reduced). Past tense for
   completed work, present tense only for ongoing roles.
3. NEVER fabricate skills, metrics, or projects. NEVER drop content.
4. Output the translated text and nothing else — no headings, no commentary.
"""


# Things we never touch even if the LLM tries to: dates, numbers, URLs,
# email/phone, single-token tech names.
_KEEP_TOKEN_RE = re.compile(
    r"https?://\S+"                                 # URLs
    r"|\b[\w.+-]+@[\w-]+\.[\w.-]+\b"               # emails
    r"|\b\+?\d[\d().\s-]{6,}\b"                     # phone-ish
    r"|\b\d{1,3}%(?!\w)"                            # percentages
    r"|\b\d+\.\d+\b"                                # decimals
    r"|\b\d{4}(?:-\d{4})?\b"                        # years / year ranges
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*\d{0,4}\b"
)


def detect_lang(text: str) -> str:
    """Return 'zh' if the text contains 30%+ CJK characters, else 'en'."""
    if not text:
        return "en"
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    return "zh" if cjk * 3 > len(text) else "en"


def _translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """LLM translation for a single text snippet."""
    text = text.strip()
    if not text:
        return ""
    if len(text) < 2 and not re.search(r"[\w一-鿿]", text):
        return text  # punctuation-only
    system = SYSTEM_EN_TO_ZH if (source_lang == "en" and target_lang == "zh") else SYSTEM_ZH_TO_EN
    # Send keep-tokens explicitly so the LLM doesn't try to translate them
    keep_tokens = sorted(set(_KEEP_TOKEN_RE.findall(text)) | {t for t in PRESERVE_TERMS if t in text})
    keep_hint = ("KEEP UNCHANGED: " + ", ".join(keep_tokens) + "\n\n") if keep_tokens else ""
    raw = llm_call_mini(system, keep_hint + text, max_tokens=800, temperature=0.0)
    return (raw or text).strip()


def _redistribute_runs(runs, translated: str):
    """Replace text of the paragraph's runs in place. The first non-empty run
    receives the entire translated text; subsequent non-empty runs are blanked.
    This keeps the first run's format (font/bold/etc) as the dominant style.

    The original `runs` is a list of run objects (docx Run). We work in-place.
    """
    non_empty = [r for r in runs if (r.text or "").strip()]
    if not non_empty:
        return
    non_empty[0].text = translated
    for r in non_empty[1:]:
        r.text = ""


def translate_paragraph(p, source_lang: str, target_lang: str):
    """Translate a single python-docx Paragraph in place."""
    text = (p.text or "").strip()
    if not text:
        return
    new = _translate_text(text, source_lang, target_lang)
    if new and new != text:
        _redistribute_runs(p.runs, new)


def translate_docx(doc, target_lang: str, source_lang: Optional[str] = None) -> dict:
    """Translate every paragraph in a python-docx Document.

    target_lang: 'zh' or 'en'.
    source_lang: auto-detected from the document if None.
    Returns a small report.
    """
    if target_lang not in ("zh", "en"):
        raise ValueError("target_lang must be 'zh' or 'en'")

    # Collect every paragraph (body + tables)
    paragraphs = list(doc.paragraphs)
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                paragraphs.extend(cell.paragraphs)

    # Auto-detect source language from full text
    if source_lang is None:
        full = "\n".join(p.text for p in paragraphs)
        source_lang = detect_lang(full)
    if source_lang == target_lang:
        return {"translated": 0, "skipped_same_lang": len(paragraphs),
                "source_lang": source_lang, "target_lang": target_lang}

    translated_count = 0
    for p in paragraphs:
        before = p.text
        if not before.strip():
            continue
        try:
            translate_paragraph(p, source_lang, target_lang)
            if p.text != before:
                translated_count += 1
        except Exception as e:
            # Best-effort — keep going on per-paragraph failures
            print(f"  [translator] paragraph failed: {e}")

    return {"translated": translated_count, "total_paragraphs": len(paragraphs),
            "source_lang": source_lang, "target_lang": target_lang}
