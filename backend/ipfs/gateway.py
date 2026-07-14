import httpx

from config import IPFS_GATEWAY, IPFS_FETCH_TIMEOUT

_HEADERS = {"Ngrok-Skip-Browser-Warning": "true"}


async def fetch_bytes(cid: str) -> bytes:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(float(IPFS_FETCH_TIMEOUT)),
        follow_redirects=True,
    ) as client:
        resp = await client.get(
            f"{IPFS_GATEWAY}/ipfs/{cid}",
            headers=_HEADERS,
        )
        resp.raise_for_status()
        return resp.content


async def fetch_json(cid: str) -> dict:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(60.0),
        follow_redirects=True,
    ) as client:
        resp = await client.get(
            f"{IPFS_GATEWAY}/ipfs/{cid}",
            headers=_HEADERS,
        )
        resp.raise_for_status()
        return resp.json()
