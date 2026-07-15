import io
import json
import traceback
import logging
import base64

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from satellite.config import CATALOG_FILE, NODE_IPS, NODE_NAMES
from satellite.processor import get_catalog, reconstruct_image

router = APIRouter(prefix="/api/satellite", tags=["satellite"])
logger = logging.getLogger("satellite")


@router.get("/status")
async def status():
    catalog = get_catalog()
    if not catalog or "images" not in catalog:
        return {"ready": False, "message": "Upload an image to get started", "total": 0, "processed": 0, "dataset": ""}
    n_ipfs = sum(1 for img in catalog["images"] if img.get("ipfs_ready"))
    return {
        "ready": n_ipfs == catalog["total"],
        "total": catalog["total"],
        "processed": n_ipfs,
        "dataset": catalog["dataset"],
    }


@router.get("/catalog")
async def catalog():
    cat = get_catalog()
    if not cat or "images" not in cat:
        return {
            "dataset": "No data yet",
            "total": 0,
            "nodes": {name: NODE_IPS[name] for name in NODE_NAMES},
            "images": [],
        }

    images = []
    for img in cat["images"]:
        essential = img.get("essential_share", {})
        shares_info = []
        for s in img.get("shares", []):
            shares_info.append({
                "index": s["index"],
                "node": s["node"],
                "node_ip": s["node_ip"],
                "hex_prefix": s["hex_prefix"],
                "cid": s["cid"],
                "thumbnail": s.get("thumbnail", ""),
            })
        images.append({
            "id": img["id"],
            "index": img["index"],
            "lat": img["lat"],
            "lon": img["lon"],
            "season": img["season"],
            "sensor": img["sensor"],
            "resolution_m": img["resolution_m"],
            "acquisition_date": img["acquisition_date"],
            "cloud_cover": img.get("cloud_cover", 0),
            "file_size": img["file_size"],
            "thumbnail": img["thumbnail"],
            "essential_share": {
                "index": essential.get("index", 0),
                "hex_prefix": essential.get("hex_prefix", ""),
                "thumbnail": essential.get("thumbnail", ""),
            },
            "shares": shares_info,
        })

    return {
        "dataset": cat["dataset"],
        "total": cat["total"],
        "nodes": {name: NODE_IPS[name] for name in NODE_NAMES},
        "images": images,
    }


@router.post("/reconstruct/{img_id}")
async def reconstruct(img_id: str):
    try:
        result = await reconstruct_image(img_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Reconstruct failed for %s: %s\n%s", img_id, e, traceback.format_exc())
        raise HTTPException(502, f"Reconstruct error: {e}")

    import os
    import hashlib

    data_path = result.get("data_path")

    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    try:
        if data_path:
            img = Image.open(data_path)
        else:
            img = Image.open(io.BytesIO(result["data"]))
        if img.mode not in ("RGB", "RGBA", "L"):
            img = img.convert("RGB")
        img.thumbnail((512, 512))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
    except Exception:
        if data_path:
            with open(data_path, "rb") as f:
                png_bytes = f.read()
        else:
            png_bytes = result["data"]

    if data_path:
        h = hashlib.sha256()
        with open(data_path, "rb") as f:
            for chunk in iter(lambda: f.read(64 * 1024 * 1024), b""):
                h.update(chunk)
        integrity = h.hexdigest()[:16]
        try:
            os.unlink(data_path)
        except Exception:
            pass
    else:
        integrity = hashlib.sha256(result["data"]).hexdigest()[:16]

    essential = result.get("essential_share", {})
    all_shares = [{
        "index": essential.get("index", 0),
        "hex_prefix": essential.get("hex_prefix", ""),
        "node": "LOCAL",
        "node_ip": "—",
        "cid": "—",
    }] + result.get("shares", [])

    return {
        "image": base64.b64encode(png_bytes).decode("ascii"),
        "duration_ms": result["reconstruct_duration_ms"],
        "sensor": result["image"]["sensor"],
        "season": result["image"]["season"],
        "integrity": integrity,
        "shares": all_shares,
        "metrics": result.get("metrics", {}),
    }
