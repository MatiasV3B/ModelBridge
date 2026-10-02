"""Test for files endpoint."""

import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from server.app import app


def test_files():
    client = TestClient(app)

    # 1. Upload a file
    dummy_content = b"Antigravity Bridge test file content."
    files = {"file": ("test_doc.txt", io.BytesIO(dummy_content), "text/plain")}
    data = {"purpose": "assistants"}

    upload_resp = client.post("/v1/files", files=files, data=data)
    assert upload_resp.status_code == 200, f"Upload failed: {upload_resp.text}"
    uploaded = upload_resp.json()
    file_id = uploaded["id"]
    print(f"File uploaded successfully with ID: {file_id}")
    assert uploaded["filename"] == "test_doc.txt"
    assert uploaded["bytes"] == len(dummy_content)

    # 2. List files
    list_resp = client.get("/v1/files")
    assert list_resp.status_code == 200
    file_list = list_resp.json()["data"]
    ids = [f["id"] for f in file_list]
    assert file_id in ids, "Uploaded file not in list"

    # 3. Retrieve metadata
    meta_resp = client.get(f"/v1/files/{file_id}")
    assert meta_resp.status_code == 200
    assert meta_resp.json()["id"] == file_id

    # 4. Retrieve content
    content_resp = client.get(f"/v1/files/{file_id}/content")
    assert content_resp.status_code == 200
    assert content_resp.content == dummy_content

    # 5. Delete file
    del_resp = client.delete(f"/v1/files/{file_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

    # 6. Verify 404 after deletion
    get_after_del = client.get(f"/v1/files/{file_id}")
    assert get_after_del.status_code == 404

    print("Files endpoint test PASSED successfully!")


if __name__ == "__main__":
    test_files()
