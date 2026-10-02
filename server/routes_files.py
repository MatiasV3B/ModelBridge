"""OpenAI Files API endpoints."""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from typing import Optional
from core.file_store import file_store

router = APIRouter(tags=["Files"])


@router.post("/v1/files")
@router.post("/files")
async def upload_file(
    file: UploadFile = File(...),
    purpose: str = Form("assistants")
):
    """Upload a file to Antigravity Bridge."""
    try:
        content = await file.read()
        file_info = file_store.save_file(
            filename=file.filename or "uploaded_file",
            content_bytes=content,
            purpose=purpose
        )
        return {
            "id": file_info["id"],
            "object": "file",
            "bytes": file_info["bytes"],
            "created_at": file_info["created_at"],
            "filename": file_info["filename"],
            "purpose": file_info["purpose"],
            "status": file_info["status"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {e}")


@router.get("/v1/files")
@router.get("/files")
async def list_files(purpose: Optional[str] = None):
    """List uploaded files."""
    files = file_store.list_files(purpose=purpose)
    return {
        "object": "list",
        "data": files
    }


@router.get("/v1/files/{file_id}")
@router.get("/files/{file_id}")
async def retrieve_file(file_id: str):
    """Retrieve metadata for a specific file."""
    info = file_store.get_file(file_id)
    if not info:
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "id": info["id"],
        "object": "file",
        "bytes": info["bytes"],
        "created_at": info["created_at"],
        "filename": info["filename"],
        "purpose": info["purpose"],
        "status": info["status"],
    }


@router.get("/v1/files/{file_id}/content")
@router.get("/files/{file_id}/content")
async def retrieve_file_content(file_id: str):
    """Download the content of a file."""
    path = file_store.get_file_path(file_id)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="File content not found")
    return FileResponse(path=path, filename=path.name)


@router.delete("/v1/files/{file_id}")
@router.delete("/files/{file_id}")
async def delete_file(file_id: str):
    """Delete a file."""
    success = file_store.delete_file(file_id)
    if not success:
        raise HTTPException(status_code=404, detail="File not found")
    return {
        "id": file_id,
        "object": "file",
        "deleted": True,
    }
