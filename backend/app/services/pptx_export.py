from __future__ import annotations

import re
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt


def _flush_slide(prs: Presentation, title: str, bullets: list[str]) -> None:
    layout = prs.slide_layouts[1]  # title + content
    slide = prs.slides.add_slide(layout)
    slide.shapes.title.text = title[:200] or "内容"
    body = slide.shapes.placeholders[1].text_frame
    body.clear()
    if not bullets:
        p = body.paragraphs[0]
        p.text = "（本节无摘要条目）"
        p.font.size = Pt(18)
        return
    first = True
    for item in bullets[:12]:
        if first:
            p = body.paragraphs[0]
            first = False
        else:
            p = body.add_paragraph()
        p.text = item[:500]
        p.level = 0
        p.font.size = Pt(18)


def markdown_to_pptx(md: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    cover_title = "调研报告"
    sections: list[tuple[str, list[str]]] = []
    current_title: str | None = None
    current_bullets: list[str] = []
    saw_h1 = False

    def close_section() -> None:
        nonlocal current_title, current_bullets
        if current_title is not None:
            sections.append((current_title, list(current_bullets)))
        current_title = None
        current_bullets = []

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("# ") and not line.startswith("##"):
            text = line[2:].strip()
            if not saw_h1:
                cover_title = text or cover_title
                saw_h1 = True
            else:
                close_section()
                current_title = text or "章节"
            continue
        if line.startswith("## "):
            close_section()
            current_title = line[3:].strip() or "章节"
            continue
        if current_title is None:
            # body before any H2 → put under「摘要」
            current_title = "摘要"
        if line.startswith("### "):
            current_bullets.append(line[4:].strip())
        elif re.match(r"^[-*]\s+", line):
            current_bullets.append(re.sub(r"^[-*]\s+", "", line).strip())
        elif re.match(r"^\d+\.\s+", line):
            current_bullets.append(re.sub(r"^\d+\.\s+", "", line).strip())
        else:
            current_bullets.append(line.strip())

    close_section()

    # cover
    cover = prs.slides.add_slide(prs.slide_layouts[0])
    cover.shapes.title.text = cover_title[:200]
    if len(cover.placeholders) > 1:
        cover.placeholders[1].text = "AI办公搭子 · 自动生成"

    if not sections:
        _flush_slide(prs, "正文", [line.strip() for line in md.splitlines() if line.strip()][:12] or ["（空报告）"])
    else:
        for title, bullets in sections:
            _flush_slide(prs, title, bullets)

    tmp = dest.with_suffix(dest.suffix + ".tmp")
    prs.save(tmp)
    Path(tmp).replace(dest)
    return dest


def ensure_pptx_from_markdown(md_path: Path, pptx_path: Path) -> Path:
    md = md_path.read_text(encoding="utf-8")
    return markdown_to_pptx(md, pptx_path)
