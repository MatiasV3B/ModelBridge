"""File management compatible with the OpenAI Files API."""

import os
import time
import json
import uuid
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
from core.config import FILES_DIR

METADATA_FILE = FILES_DIR / "_metadata.json"


class FileStore:
    def __init__(self, directory: Path = FILES_DIR):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.metadata_file = self.directory / "_metadata.json"
        self._load_metadata()

    def _load_metadata(self):
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    self.files: Dict[str, Dict[str, Any]] = json.load(f)
                    return
            except Exception:
                pass
        self.files = {}

    def _save_metadata(self):
        try:
            with open(self.metadata_file, "w", encoding="utf-8") as f:
                json.dump(self.files, f, indent=2)
        except Exception as e:
            print(f"Error saving file metadata: {e}")

    def save_file(self, filename: str, content_bytes: bytes, purpose: str = "assistants") -> Dict[str, Any]:
        """Save a new file and return its OpenAI-compatible metadata."""
        file_id = f"file-{uuid.uuid4().hex[:12]}"
        safe_filename = Path(filename).name
        target_path = self.directory / f"{file_id}_{safe_filename}"

        with open(target_path, "wb") as f:
            f.write(content_bytes)

        file_info = {
            "id": file_id,
            "object": "file",
            "bytes": len(content_bytes),
            "created_at": int(time.time()),
            "filename": safe_filename,
            "purpose": purpose,
            "status": "processed",
            "local_path": str(target_path),
        }

        self.files[file_id] = file_info
        self._save_metadata()
        return file_info

    def list_files(self, purpose: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all stored files."""
        result = []
        for file_info in self.files.values():
            if purpose and file_info.get("purpose") != purpose:
                continue
            # Return without internal local_path in standard response if preferred, or keep it
            clean_info = {k: v for k, v in file_info.items() if k != "local_path"}
            result.append(clean_info)
        # Sort by creation time descending
        result.sort(key=lambda x: x["created_at"], reverse=True)
        return result

    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific file."""
        return self.files.get(file_id)

    def get_file_path(self, file_id: str) -> Optional[Path]:
        """Get absolute path on disk for a file."""
        info = self.files.get(file_id)
        if not info:
            return None
        path = Path(info["local_path"])
        return path if path.exists() else None

    def delete_file(self, file_id: str) -> bool:
        """Delete a file from disk and metadata."""
        if file_id in self.files:
            info = self.files[file_id]
            try:
                path = Path(info.get("local_path", ""))
                if path.exists():
                    os.remove(path)
            except Exception:
                pass
            del self.files[file_id]
            self._save_metadata()
            return True
        return False


file_store = FileStore()
