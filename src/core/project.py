"""Project model: a single image sorting task with categories, progress, and history."""

from __future__ import annotations
import json, os, time, uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any

STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"


@dataclass
class Category:
    key: str                # e.g. "1", "A"
    name: str               # display name
    target_dir: str         # absolute path
    enabled: bool = True


@dataclass
class OperationRecord:
    """One undoable operation. Recorded in reverse order for undo."""
    op: str                 # "copy" | "move" | "delete"
    src_path: str           # original source path
    dst_path: Optional[str] # where it was placed (None for delete)
    category_key: Optional[str]   # which category was triggered
    timestamp: float = field(default_factory=time.time)


@dataclass
class Project:
    id: str
    name: str
    source_dir: str
    recursive: bool
    operation_mode: str                     # "copy" | "move"
    sort_field: str
    sort_descending: bool
    categories: List[Category]              # ordered
    created_at: float
    updated_at: float
    status: str = STATUS_IN_PROGRESS
    cover_image: Optional[str] = None

    # Runtime state
    file_order: List[str] = field(default_factory=list)   # absolute paths in display order
    current_index: int = -1                               # -1 = not started
    classified: Dict[str, str] = field(default_factory=dict)  # path -> category_key (for multi-classify tracking)
    history: List[OperationRecord] = field(default_factory=list)
    last_activity: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["categories"] = [asdict(c) if isinstance(c, Category) else c for c in self.categories]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Project":
        # Ignore unknown keys left behind by older builds that stored project
        # overrides in this same file.
        allowed = {
            "id", "name", "source_dir", "recursive", "operation_mode",
            "sort_field", "sort_descending", "categories", "created_at",
            "updated_at", "status", "cover_image", "file_order",
            "current_index", "classified", "history", "last_activity",
        }
        d = {k: v for k, v in d.items() if k in allowed}
        cats_raw = d.get("categories", [])
        cats: List[Category] = []
        for c in cats_raw:
            if isinstance(c, Category):
                cats.append(c)
            else:
                cats.append(Category(**c))
        d2 = dict(d)
        d2["categories"] = cats
        d2["history"] = [OperationRecord(**h) if isinstance(h, dict) else h
                         for h in d2.get("history", [])]
        return cls(**d2)


def new_project_id() -> str:
    return uuid.uuid4().hex[:12]


class ProjectStore:
    """All projects live as one JSON file at <app_dir>/projects.json (index)
    plus each project's own <app_dir>/projects/<id>/project.json (state)."""

    def __init__(self, app_dir: Path):
        self.app_dir = Path(app_dir)
        self.index_path = self.app_dir / "projects.json"
        self.projects_dir = self.app_dir / "projects"
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self._index: List[Dict[str, Any]] = []
        self._load_index()

    def _load_index(self) -> None:
        if self.index_path.exists():
            try:
                self._index = json.loads(self.index_path.read_text(encoding="utf-8"))
            except Exception:
                self._index = []
        else:
            self._index = []

    def _save_index(self) -> None:
        self.index_path.write_text(
            json.dumps(self._index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ---- CRUD on index ----
    def list_all(self) -> List[Dict[str, Any]]:
        """Return lightweight index entries (id, name, status, last_activity, cover)."""
        return list(self._index)

    def get_meta(self, pid: str) -> Optional[Dict[str, Any]]:
        for entry in self._index:
            if entry.get("id") == pid:
                return entry
        return None

    def upsert_meta(self, meta: Dict[str, Any]) -> None:
        pid = meta["id"]
        for i, e in enumerate(self._index):
            if e.get("id") == pid:
                self._index[i] = meta
                self._save_index()
                return
        self._index.append(meta)
        self._save_index()

    def delete(self, pid: str) -> None:
        self._index = [e for e in self._index if e.get("id") != pid]
        self._save_index()
        proj_dir = self.projects_dir / pid
        if proj_dir.exists():
            import shutil
            shutil.rmtree(proj_dir, ignore_errors=True)

    # ---- Full project load/save ----
    def project_file(self, pid: str) -> Path:
        return self.projects_dir / pid / "project.json"

    def load_project(self, pid: str) -> Optional[Project]:
        pf = self.project_file(pid)
        if not pf.exists():
            return None
        try:
            d = json.loads(pf.read_text(encoding="utf-8"))
            return Project.from_dict(d)
        except Exception:
            return None

    def save_project(self, project: Project) -> None:
        project.updated_at = time.time()
        project.last_activity = project.updated_at
        pf = self.project_file(project.id)
        pf.parent.mkdir(parents=True, exist_ok=True)
        pf.write_text(
            json.dumps(project.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # Mirror lightweight metadata into the index for fast list views.
        meta = {
            "id": project.id,
            "name": project.name,
            "source_dir": project.source_dir,
            "status": project.status,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "last_activity": project.last_activity,
            "cover_image": project.cover_image,
            "current_index": project.current_index,
            "total": len(project.file_order),
            "categories": [asdict(c) if isinstance(c, Category) else c for c in project.categories],
            "operation_mode": project.operation_mode,
            "sort_field": project.sort_field,
            "sort_descending": project.sort_descending,
        }
        self.upsert_meta(meta)
