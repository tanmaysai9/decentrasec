import json
from pathlib import Path
from typing import Optional

from config import MANIFESTS_FILE


def _ensure_file():
    p = Path(MANIFESTS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text("{}", encoding="utf-8")


def load_manifests() -> dict:
    _ensure_file()
    return json.loads(Path(MANIFESTS_FILE).read_text(encoding="utf-8"))


def save_manifests(data: dict):
    _ensure_file()
    Path(MANIFESTS_FILE).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def add_manifest(manifest: dict):
    all_data = load_manifests()
    all_data[manifest["id"]] = manifest
    save_manifests(all_data)


def get_manifest(manifest_id: str) -> Optional[dict]:
    return load_manifests().get(manifest_id)


def get_manifests_for_address(address: str) -> list[dict]:
    all_data = load_manifests()
    results = []
    for m in all_data.values():
        if m.get("owner_address") == address:
            results.append(m)
    return sorted(results, key=lambda x: x.get("created_at", ""), reverse=True)


def delete_manifest(manifest_id: str) -> bool:
    all_data = load_manifests()
    if manifest_id in all_data:
        del all_data[manifest_id]
        save_manifests(all_data)
        return True
    return False


def update_manifest(manifest_id: str, updates: dict):
    all_data = load_manifests()
    if manifest_id in all_data:
        all_data[manifest_id].update(updates)
        save_manifests(all_data)
