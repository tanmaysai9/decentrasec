import base64
import json

import httpx

from config import (
    IPFS_CLUSTER_API,
    IPFS_CLUSTER_USER,
    IPFS_CLUSTER_PASS,
    IPFS_UPLOAD_TIMEOUT,
)

_CREDS = base64.b64encode(f"{IPFS_CLUSTER_USER}:{IPFS_CLUSTER_PASS}".encode()).decode()

_HEADERS = {
    "Authorization": f"Basic {_CREDS}",
    "Ngrok-Skip-Browser-Warning": "true",
}


def _extract_cid(val):
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("/") or val.get("Cid", {}).get("/") or str(val)
    return str(val)


def _parse_cid(text: str) -> str:
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        cid_val = obj.get("cid")
        if cid_val and obj.get("name"):
            return _extract_cid(cid_val)
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        cid_val = obj.get("cid")
        if cid_val:
            return _extract_cid(cid_val)
    raise ValueError(f"No CID found in response: {text[:200]}")


async def upload_json(obj_bytes: bytes) -> str:
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        resp = await client.post(
            f"{IPFS_CLUSTER_API}/add",
            headers=_HEADERS,
            files={"file": ("manifest.json", obj_bytes, "application/json")},
            data={"pin": "true"},
        )
        resp.raise_for_status()
        return _parse_cid(resp.text)
