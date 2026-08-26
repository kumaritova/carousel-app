import os

from pypdf import PdfReader
from docx import Document


def extract_text(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".pdf":
            reader = PdfReader(file_path)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        if ext == ".docx":
            doc = Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs)
        if ext in (".txt", ".md"):
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                return f.read()
    except Exception as e:
        return f"[Не удалось прочитать файл {os.path.basename(file_path)}: {e}]"
    return ""
