import json
import logging

import httpx

from config import NODE_IPS, NODE_DAEMON_PORT, NODE_GATEWAY_PORT, IPFS_UPLOAD_TIMEOUT

logger = logging.getLogger("ipfs.node")


def _daemon_url(node_name: str) -> str:
    ip = NODE_IPS[node_name]
    return f"http://{ip}:{NODE_DAEMON_PORT}"


def _gateway_url(node_name: str) -> str:
    ip = NODE_IPS[node_name]
    return f"http://{ip}:{NODE_GATEWAY_PORT}"


async def upload_to_node(node_name: str, data: bytes, filename: str = "share") -> str:
    url = f"{_daemon_url(node_name)}/api/v0/add?pin=true"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(float(IPFS_UPLOAD_TIMEOUT)),
    ) as client:
        resp = await client.post(
            url,
            files={"file": (filename, data, "application/octet-stream")},
        )
        resp.raise_for_status()
        for line in resp.text.strip().splitlines():
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("Hash") and obj.get("Name") and obj["Name"] != "":
                return obj["Hash"]
        raise ValueError(f"No Hash in response from {node_name}: {resp.text[:200]}")


async def fetch_from_node(node_name: str, cid: str) -> bytes:
    url = f"{_gateway_url(node_name)}/ipfs/{cid}"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(float(IPFS_UPLOAD_TIMEOUT)),
        follow_redirects=True,
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


async def check_node_health(node_name: str) -> dict:
    try:
        url = f"{_daemon_url(node_name)}/api/v0/id"
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            resp = await client.post(url)
            resp.raise_for_status()
            data = resp.json()
            return {
                "name": node_name,
                "ip": NODE_IPS[node_name],
                "status": "online",
                "peer_id": data.get("ID", ""),
            }
    except Exception as e:
        return {
            "name": node_name,
            "ip": NODE_IPS[node_name],
            "status": "offline",
            "error": str(e),
        }
