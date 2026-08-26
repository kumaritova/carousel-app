from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECTS_DIR = os.path.join(BASE_DIR, "storage", "projects")
UPLOADS_DIR = os.path.join(BASE_DIR, "storage", "uploads")

os.makedirs(PROJECTS_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

FIELDS = [
    "name",
    "business_description",
    "product_offer",
    "target_audience",
    "positioning",
    "tone_of_voice",
    "content_goal",
    "extra_instructions",
    "user_notes",
]

MAX_HISTORY = 30


def _project_path(project_id: str) -> str:
    return os.path.join(PROJECTS_DIR, f"{project_id}.json")


def _uploads_dir(project_id: str) -> str:
    path = os.path.join(UPLOADS_DIR, project_id)
    os.makedirs(path, exist_ok=True)
    return path


def list_projects() -> list[dict]:
    projects = []
    for fname in os.listdir(PROJECTS_DIR):
        if fname.endswith(".json"):
            with open(os.path.join(PROJECTS_DIR, fname), encoding="utf-8") as f:
                data = json.load(f)
                projects.append(data)
    projects.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
    return projects


def load_project(project_id: str) -> dict | None:
    path = _project_path(project_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("materials", [])
    data.setdefault("history", [])
    for field in FIELDS:
        data.setdefault(field, "")
    return data


def create_project(name: str) -> dict:
    project_id = str(uuid.uuid4())
    now = datetime.now().isoformat(timespec="seconds")
    data = {field: "" for field in FIELDS}
    data.update(
        {
            "id": project_id,
            "name": name or "Новый проект",
            "created_at": now,
            "updated_at": now,
            "materials": [],
            "history": [],
        }
    )
    save_project(data)
    return data


def save_project(data: dict) -> None:
    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
    with open(_project_path(data["id"]), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def delete_project(project_id: str) -> None:
    path = _project_path(project_id)
    if os.path.exists(path):
        os.remove(path)


def save_uploaded_file(project_id: str, filename: str, content: bytes) -> str:
    target_dir = _uploads_dir(project_id)
    safe_name = f"{uuid.uuid4().hex}_{filename}"
    full_path = os.path.join(target_dir, safe_name)
    with open(full_path, "wb") as f:
        f.write(content)
    return full_path


def remove_material_file(file_path: str) -> None:
    if file_path and os.path.exists(file_path):
        os.remove(file_path)


def add_user_note(project: dict, note: str) -> bool:
    """Appends a revision note to the project's user_notes, skipping it if an
    equivalent note is already stored. Returns True if the note was added."""
    note = note.strip()
    if not note:
        return False
    existing = project.get("user_notes") or ""
    if note.lower() in existing.lower():
        return False
    project["user_notes"] = f"{existing}\n- {note}".strip() if existing else f"- {note}"
    save_project(project)
    return True


def add_history_entry(project: dict, entry: dict) -> None:
    entry["id"] = str(uuid.uuid4())
    entry["created_at"] = datetime.now().isoformat(timespec="seconds")
    history = project.setdefault("history", [])
    history.insert(0, entry)
    del history[MAX_HISTORY:]
    save_project(project)
