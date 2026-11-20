from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional
from app.services.event_calendar import get_access_token

import httpx


GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphError(RuntimeError):
    pass


@dataclass
class SharePointConfig:
    hostname: str
    site_path: str
    library_name: str = "Documents"
    root_folder: str = "audit-reports-2026"
    plants_folder: str = "Plants"  
    guidelines_root_folder: str = "Questionnaires-guidelines"


def _safe_sp_name(name: str) -> str:
    """
    Make a SharePoint-safe folder/file name.
    Removes forbidden chars: " * : < > ? / \ | and trims dots/spaces.
    """
    name = (name or "").strip()
    if not name:
        return "Unknown-Plant"
    name = re.sub(r'[\"*:<>?/\\|]+', "-", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(". ")
    return name or "Unknown-Plant"


class SharePointAuditStorage:
    def __init__(self, cfg: SharePointConfig):
        self.cfg = cfg

    async def _headers(self) -> Dict[str, str]:
        token = await get_access_token()
        return {"Authorization": f"Bearer {token}"}

    async def _get_json(self, url: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(url, headers=await self._headers())
            if r.status_code >= 400:
                raise GraphError(f"GET {url} -> {r.status_code}: {r.text}")
            return r.json()

    async def _post_json(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            headers = await self._headers()
            headers["Content-Type"] = "application/json"
            r = await client.post(url, headers=headers, json=payload)
            if r.status_code >= 400:
                raise GraphError(f"POST {url} -> {r.status_code}: {r.text}")
            return r.json()

    async def _put_bytes(self, url: str, data: bytes, content_type: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=120) as client:
            headers = await self._headers()
            headers["Content-Type"] = content_type
            r = await client.put(url, headers=headers, content=data)
            if r.status_code >= 400:
                raise GraphError(f"PUT {url} -> {r.status_code}: {r.text}")
            return r.json()

    async def _delete(self, url: str) -> None:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.delete(url, headers=await self._headers())
            if r.status_code in (204, 200):
                return
            if r.status_code == 404:
                return
            raise GraphError(f"DELETE {url} -> {r.status_code}: {r.text}")

    # ---------- Lookups ----------
    async def get_site_id(self) -> str:
        url = f"{GRAPH_BASE}/sites/{self.cfg.hostname}:{self.cfg.site_path}"
        site = await self._get_json(url)
        return site["id"]

    async def get_drive_id(self, site_id: str) -> str:
        url = f"{GRAPH_BASE}/sites/{site_id}/drives"
        drives = await self._get_json(url)
        for d in drives.get("value", []):
            if d.get("name") == self.cfg.library_name:
                return d["id"]
        available = [d.get("name") for d in drives.get("value", [])]
        raise GraphError(f"Drive '{self.cfg.library_name}' not found. Available: {available}")

    async def get_item_by_path(self, drive_id: str, sp_path: str) -> Dict[str, Any]:
        sp_path = sp_path.lstrip("/")
        url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{sp_path}"
        return await self._get_json(url)

    async def ensure_folder_path(self, drive_id: str, folder_path: str) -> Dict[str, Any]:
        """
        Ensure nested folder path exists under root, create level-by-level.
        Returns final folder item.
        """
        parts = [p for p in folder_path.strip("/").split("/") if p]
        if not parts:
            raise ValueError("folder_path empty")

        current_path = ""
        current_item: Optional[Dict[str, Any]] = None

        # Get root item id once
        root_item = await self._get_json(f"{GRAPH_BASE}/drives/{drive_id}/root")
        root_id = root_item["id"]

        parent_id = root_id
        for idx, part in enumerate(parts):
            current_path = f"{current_path}/{part}" if current_path else part
            try:
                current_item = await self.get_item_by_path(drive_id, current_path)
                parent_id = current_item["id"]
                continue
            except GraphError as e:
                if "-> 404" not in str(e):
                    raise

            # Create folder under parent_id
            payload = {
                "name": part,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "rename",
            }
            created = await self._post_json(f"{GRAPH_BASE}/drives/{drive_id}/items/{parent_id}/children", payload)
            current_item = created
            parent_id = created["id"]

        if not current_item:
            raise GraphError("Failed to ensure folder path")
        return current_item

    # ---------- Paths ----------
    def plant_folder_path(self, plant_name: str) -> str:
        plant_safe = _safe_sp_name(plant_name)
        return f"{self.cfg.root_folder}/{self.cfg.plants_folder}/{plant_safe}"

    def report_file_path(self, plant_name: str, filename: str) -> str:
        plant_path = self.plant_folder_path(plant_name)
        filename_safe = _safe_sp_name(filename)
        return f"{plant_path}/{filename_safe}"

    # ---------- Upload / Delete / Download ----------
    async def upload_report_to_plant(
        self,
        plant_name: str,
        pdf_path: Path,
        filename: str,
    ) -> Dict[str, Any]:
        site_id = await self.get_site_id()
        drive_id = await self.get_drive_id(site_id)

        # Ensure plant folder exists
        plant_path = self.plant_folder_path(plant_name)
        await self.ensure_folder_path(drive_id, plant_path)

        # Upload
        sp_file_path = self.report_file_path(plant_name, filename)
        data = Path(pdf_path).read_bytes()
        uploaded = await self._put_bytes(
            f"{GRAPH_BASE}/drives/{drive_id}/root:/{sp_file_path}:/content",
            data=data,
            content_type="application/pdf",
        )

        return {
            "site_id": site_id,
            "drive_id": drive_id,
            "file": {
                "id": uploaded.get("id"),
                "name": uploaded.get("name"),
                "webUrl": uploaded.get("webUrl"),
                "path": sp_file_path,
            },
        }

    async def delete_by_item_id(self, drive_id: str, item_id: str) -> None:
        await self._delete(f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}")

    async def delete_by_path_if_exists(self, drive_id: str, sp_file_path: str) -> None:
        """
        Delete file if it exists (by path). No error if missing.
        """
        sp_file_path = sp_file_path.lstrip("/")
        # Resolve item by path then delete by id
        try:
            item = await self.get_item_by_path(drive_id, sp_file_path)
        except GraphError as e:
            if "-> 404" in str(e):
                return
            raise
        await self.delete_by_item_id(drive_id, item["id"])

    async def download_content_stream(self, drive_id: str, item_id: str) -> httpx.Response:
        """
        Return an httpx.Response streaming the bytes of the file content.
        Caller must stream it to FastAPI response.
        """
        url = f"{GRAPH_BASE}/drives/{drive_id}/items/{item_id}/content"
        client = httpx.AsyncClient(timeout=None)  # we'll close after streaming
        r = await client.get(url, headers=await self._headers(), follow_redirects=True)
        if r.status_code >= 400:
            await client.aclose()
            raise GraphError(f"GET content -> {r.status_code}: {r.text}")
        # Attach client to response for later closing
        r._sp_client = client  # type: ignore[attr-defined]
        return r

    async def close_stream(self, r: httpx.Response) -> None:
        client = getattr(r, "_sp_client", None)
        if client:
            await client.aclose()


# -------------------------
class SharePointGuidelineStorage:
    def __init__(self, sp_base: SharePointAuditStorage):
        self.sp = sp_base
        self.cfg = sp_base.cfg

    def guideline_file_path_flat(self, filename: str) -> str:
            """Store directly under guidelines_root_folder without ID subfolder"""
            return f"{self.cfg.guidelines_root_folder}/{_safe_sp_name(filename)}"

    async def upload_guideline_flat(
            self,
            file_bytes: bytes,
            filename: str,
            content_type: str,
        ) -> dict:
            """Upload guideline directly to Questionnaires-guidelines folder (no ID subfolder)"""
            site_id = await self.sp.get_site_id()
            drive_id = await self.sp.get_drive_id(site_id)

            # Ensure root guidelines folder exists
            await self.sp.ensure_folder_path(drive_id, self.cfg.guidelines_root_folder)

            # Upload directly to root guidelines folder
            sp_path = self.guideline_file_path_flat(filename)

            # Use upload session for files (supports large files)
            uploaded = await self._upload_via_session(
                drive_id=drive_id,
                sp_file_path=sp_path,
                data=file_bytes,
                content_type=content_type or "application/octet-stream",
            )

            return {
                "site_id": site_id,
                "drive_id": drive_id,
                "file": {
                    "id": uploaded.get("id"),
                    "name": uploaded.get("name"),
                    "webUrl": uploaded.get("webUrl"),
                    "path": sp_path,
                },
            }
    
    async def delete_guideline(self, drive_id: str, item_id: str) -> None:
        await self.sp.delete_by_item_id(drive_id, item_id)

    async def _upload_via_session(self, drive_id: str, sp_file_path: str, data: bytes, content_type: str) -> dict:
        create_url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{sp_file_path}:/createUploadSession"
        payload = {"item": {"@microsoft.graph.conflictBehavior": "replace"}}
        session = await self.sp._post_json(create_url, payload)  # re-use your base helper
        upload_url = session["uploadUrl"]

        chunk_size = 5 * 1024 * 1024  # 5MB chunks
        total = len(data)
        start = 0

        async with httpx.AsyncClient(timeout=120) as client:
            while start < total:
                end = min(start + chunk_size, total) - 1
                chunk = data[start : end + 1]
                headers = {
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end}/{total}",
                    "Content-Type": content_type,
                }
                r = await client.put(upload_url, headers=headers, content=chunk)

                if r.status_code in (200, 201):
                    return r.json()
                if r.status_code == 202:
                    start = end + 1
                    continue

                raise GraphError(f"Upload session chunk failed: {r.status_code}: {r.text}")

        raise GraphError("Upload session did not complete")

