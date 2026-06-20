from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "")
    return text.strip()


def infer_category(path: Path) -> str:
    parts = set(path.parts)
    name = path.name
    if "教具说明书" in parts or "说明书" in name:
        return "manual"
    if "小学科学" in parts or "小学科学" in name:
        return "primary_science"
    if "跨学科" in parts or "跨学科" in name or "STEAM" in name.upper():
        return "cross_discipline"
    if "初高中" in parts or "高中" in name or "中学" in name or "物理" in name:
        return "middle_high_physics"
    if "玩具" in parts or "玩具" in name:
        return "toy_design"
    return "reference"


def infer_level(path: Path) -> str:
    text = str(path)
    if "小学" in text or "幼儿" in text:
        return "小学"
    if "初中" in text or "八年级" in text or "九年级" in text:
        return "初中"
    if "高中" in text or "高一" in text or "高考" in text:
        return "高中"
    return "通用"


def extract_pdf(path: Path, max_pages: int) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        texts = []
        for page in reader.pages[:max_pages]:
            texts.append(page.extract_text() or "")
        return clean_text(" ".join(texts))
    except Exception as exc:
        return f"[PDF解析失败: {exc}]"


def extract_docx(path: Path) -> str:
    try:
        from docx import Document

        doc = Document(str(path))
        return clean_text(" ".join(p.text for p in doc.paragraphs))
    except Exception as exc:
        return f"[DOCX解析失败: {exc}]"


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".textclipping":
        return summarize_filename(path)
    try:
        return clean_text(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as exc:
        return f"[文本解析失败: {exc}]"


def summarize_filename(path: Path) -> str:
    stem = path.stem.replace(".pdf", "")
    stem = re.sub(r"[_—-]+", " ", stem)
    return clean_text(stem)


def build(root: Path, output: Path, max_pages: int) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    suffixes = {".pdf", ".docx", ".textclipping", ".txt", ".md"}
    files = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in suffixes
        and "__MACOSX" not in path.parts
    ]
    count = 0
    with output.open("w", encoding="utf-8") as f:
        for idx, path in enumerate(sorted(files), start=1):
            suffix = path.suffix.lower()
            if suffix == ".pdf":
                content = extract_pdf(path, max_pages=max_pages)
            elif suffix == ".docx":
                content = extract_docx(path)
            else:
                content = extract_text(path)
            if not content or content.startswith("[") and len(content) < 80:
                content = summarize_filename(path)
            row = {
                "id": f"edutoy_{idx:04d}",
                "category": infer_category(path),
                "level": infer_level(path),
                "title": summarize_filename(path),
                "content": content[:5000],
                "tags": make_tags(path),
                "path": str(path),
                "source": "local_material",
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def make_tags(path: Path) -> list[str]:
    text = str(path)
    seeds = [
        "小学",
        "初中",
        "高中",
        "物理",
        "科学",
        "实验",
        "教具",
        "益智玩具",
        "跨学科",
        "STEAM",
        "Phyphox",
        "ESP32",
        "平面镜",
        "光的偏振",
        "光的干涉",
        "杠杆",
        "液体压强",
        "浮力",
        "声音",
        "热胀冷缩",
    ]
    return [seed for seed in seeds if seed in text]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="新的设计")
    parser.add_argument("--output", default="data/edutoy/documents.jsonl")
    parser.add_argument("--max-pages", type=int, default=4)
    args = parser.parse_args()
    count = build(Path(args.root), Path(args.output), args.max_pages)
    print(f"Indexed {count} documents -> {args.output}")


if __name__ == "__main__":
    main()
