# DecentraSec — Post-Quantum Secure Satellite Imagery Storage

A distributed, post-quantum secure file storage system that encrypts satellite
imagery with **AES-256-GCM** and protects the encryption key with **Non-Linear
Secret Sharing (NLSS / DMaya, 3-of-4)**. The encrypted data stays on the owner
node; only the small NLSS key shares are distributed across an IPFS cluster.

This is a **personal vault** model: each owner encrypts and reconstructs only
their own files. IPFS acts as a threshold key-escrow, not as file storage.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Cryptographic Model](#cryptographic-model)
3. [Network Topology](#network-topology)
4. [Upload Pipeline](#upload-pipeline)
5. [Reconstruction Pipeline](#reconstruction-pipeline)
6. [Data Manifest](#data-manifest)
7. [Satellite Imagery Module](#satellite-imagery-module)
8. [Authentication Model](#authentication-model)
9. [Blockchain Anchoring](#blockchain-anchoring)
10. [API Endpoints](#api-endpoints)
11. [Ngrok Tunnel Setup](#ngrok-tunnel-setup)
12. [Project Structure](#project-structure)
13. [Quick Start](#quick-start)

---

## Architecture Overview

```
CLIENT BROWSER (thin UI, zero crypto)
       |
       |  http://192.168.22.95:8000  (or ngrok)
       v
+------------------------------------------+
|  BOOTSTRAP / OWNER NODE  (192.168.22.95) |
|                                          |
|  +------------------+                    |
|  | FastAPI Backend  |  :8000             |
|  |   - AES-256-GCM encrypt/decrypt       |
|  |   - NLSS (DMaya) key split/combine    |
|  |   - Ciphertext blob store (local)     |
|  |   - Manifest store (local JSON)       |
|  |   - IPFS client (localhost)           |
|  |   - React SPA (/static/)              |
|  +--------+---------+                    |
|           |                              |
|  +--------v--+  +-----v--------+         |
|  | IPFS Daemon|  | IPFS Cluster|         |
|  |   :5001    |  |   :9094     |         |
|  |   :8080 gw |  |              |        |
|  +--------+---+  +-----+--------+        |
+-----------|------------|---------+
            |            |
   +--------+------+     |
   v       v       v     v
+-------+-------+-------+-------+-------+
| NODE-1| NODE-2| NODE-3| NODE-4| NODE-5|
| .90   | .91   | .92   | .93   | .94   |
+-------+-------+-------+-------+-------+
  Each storage node holds one NLSS key share (tiny).
  The ciphertext blob never leaves the owner node.
```

**Key principles:**
- The **ciphertext blob** (the actual encrypted file) is stored on the owner
  node's local disk. It is **not** uploaded to IPFS.
- **IPFS only stores the NLSS key shares** — a handful of ~32-byte-equivalent
  fragments of the AES key. Storage on IPFS is negligible per file.
- The **manifest** is local (`manifests.json`); it never goes to IPFS.
- All cryptography runs on the backend; the browser is a thin UI shell.

---

## Cryptographic Model

### Single scheme: AES-256-GCM + NLSS key split (3-of-4)

Every upload uses the same pipeline:

| Step | Algorithm | What it protects |
|---|---|---|
| Compress | gzip (level 6) | reduces payload size |
| Encrypt | AES-256-GCM | confidentiality + integrity of the file |
| Key split | Non-Linear Secret Sharing (DMaya 1.7), 3-of-4 | threshold protection of the AES key |
| Distribute | IPFS per-node pin | availability of the key shares |

### AES-256-GCM
- **Key:** 32 bytes (256 bits), randomly generated per file via `os.urandom`.
- **Nonce:** 12 bytes, random per encryption.
- **Authentication tag:** 16 bytes (GCM provides confidentiality + integrity).
- **Blob format:** `[12B nonce][16B tag][ciphertext]` — a single self-describing
  file written to `data/encrypted/<id>.bin`.
- **Post-quantum:** AES-256 is reduced to 128-bit effective security by Grover's
  algorithm, still considered secure.

### Non-Linear Secret Sharing (NLSS / DMaya 1.7)
- The **32-byte AES key** (not the data) is split into **4 shares** with a
  **3-of-4 threshold**. Any 3 shares reconstruct the key; ≤2 reveal nothing.
- Implemented via the external `DMaya1.7-enc` / `DMaya1.7-dec` binaries
  (`mono` runtime on Linux). Wrapped by `crypto/dmaya.py`.
- This is used here purely as a **threshold key-split** on top of standard AES
  encryption — it does not replace AES. The data confidentiality comes from AES;
  the key availability/confidentiality comes from the NLSS threshold.

> Note: the DMaya decoder binary currently requires **all 4** share files (plus
> the index) to be present for reconstruction, even though the scheme is
> cryptographically 3-of-4. Reconstruction therefore fetches all 4 shares.

### SHA-256
- SHA-256 of the **original plaintext** is stored in the manifest and verified
  after reconstruction to detect any tampering or corruption end-to-end.

### Why this design
Splitting only the 32-byte key (instead of the whole payload) means:
- **IPFS storage per file ≈ 4 × tiny key shares** (negligible), not 4× the file.
- The bulk crypto is native AES (fast); NLSS only processes 32 bytes
  (near-constant time), instead of the whole image.
- Confidentiality holds: an attacker with the ciphertext + ≤2 key shares
  recovers nothing (AES-256).

---

## Network Topology

| Machine | IP | Services | Port(s) |
|---|---|---|---|
| Bootstrap (Owner) | 192.168.22.95 | FastAPI | 8000 |
| | | IPFS Daemon | 5001 (API), 4001 (Swarm), 8080 (Gateway) |
| | | IPFS Cluster Service | 9094 (REST API) |
| NODE-1 | 192.168.22.90 | IPFS Daemon + Cluster | 4001, 5001, 8080 |
| NODE-2 | 192.168.22.91 | IPFS Daemon + Cluster | 4001, 5001, 8080 |
| NODE-3 | 192.168.22.92 | IPFS Daemon + Cluster | 4001, 5001, 8080 |
| NODE-4 | 192.168.22.93 | IPFS Daemon + Cluster | 4001, 5001, 8080 |
| NODE-5 | 192.168.22.94 | IPFS Daemon + Cluster | 4001, 5001, 8080 |

All nodes are connected via a **private IPFS swarm** (shared `swarm.key`); no
external peers can join.

---

## Upload Pipeline

`POST /api/upload` (auth required) starts an async 6-stage pipeline:

```
Stage 1: VALIDATE      - non-empty, within MAX_FILE_SIZE_MB
Stage 2: COMPRESS      - gzip.compress(file, level=6)
Stage 3: ENCRYPT       - AES-256-GCM(compressed) -> blob
                        - blob saved to data/encrypted/<id>.bin (LOCAL)
Stage 4: SPLIT         - NLSS(DMaya) splits the 32-byte AES key -> 4 shares + index
Stage 5: DISTRIBUTE    - each key share -> one storage node (:5001/api/v0/add, pin)
Stage 6: ANCHOR        - manifest saved to data/manifests.json (LOCAL)
                        - mock Merkle root + tx hash over key-share CIDs
```

**What is stored where:**

| Location | Stores |
|---|---|
| Owner node disk (`data/encrypted/`) | The AES ciphertext blob (the file) |
| `data/manifests.json` | The manifest (local JSON) |
| NODE-1 .. NODE-4 (IPFS) | One NLSS key share each (~32 B) |

The ciphertext blob and the manifest **never touch IPFS**.

---

## Reconstruction Pipeline

`POST /api/reconstruct/{manifest_id}` (owner-only):

```
1. LOAD MANIFEST        - from data/manifests.json (local)
2. FETCH KEY SHARES     - all 4 NLSS shares from their IPFS nodes (:8080 gateway)
3. RECOVER AES KEY      - NLSS(DMaya) combine -> 32-byte AES key
4. READ CIPHERTEXT      - load data/encrypted/<id>.bin from local disk
5. DECRYPT              - AES-256-GCM decrypt -> compressed
6. DECOMPRESS           - gzip.decompress -> plaintext
7. VERIFY INTEGRITY     - SHA-256(plaintext) must match manifest.sha256
```

Response headers: `X-Merkle-Root`, `X-Integrity: verified`,
`X-Shares-Used`, `X-Reconstruct-Duration-Ms`.

---

## Data Manifest

Each upload produces a local JSON manifest in `data/manifests.json`:

```json
{
  "id": "uuid",
  "owner_address": "0xA1B2...",
  "file_name": "scene.tif",
  "original_size": 52428800,
  "compressed_size": 48192000,
  "encrypted_size": 48192028,
  "mime_type": "image/tiff",
  "scheme": "DMAYA-KEY",
  "mode": "key",
  "threshold_k": 3,
  "total_shares_n": 4,
  "sha256": "<hex of original plaintext>",
  "blob_path": "data/encrypted/<id>.bin",
  "key_shares": [
    {"index": 0, "node": "NODE-1", "node_ip": "192.168.22.90", "cid": "Qm...", "rel_path": "...", "size": 96},
    {"index": 1, "node": "NODE-2", "node_ip": "192.168.22.91", "cid": "Qm...", "rel_path": "...", "size": 96},
    {"index": 2, "node": "NODE-3", "node_ip": "192.168.22.92", "cid": "Qm...", "rel_path": "...", "size": 96},
    {"index": 3, "node": "NODE-4", "node_ip": "192.168.22.93", "cid": "Qm...", "rel_path": "...", "size": 96}
  ],
  "merkle_root": "0x...",
  "tx_hash": "0x...",
  "thumbnail": "<base64 jpeg>",
  "upload_duration_ms": 1234,
  "stage_durations": {...},
  "created_at": "2026-07-13T..."
}
```

The archive list is filtered by `owner_address` — each user sees only their own
files (personal vault).

---

## Satellite Imagery Module

A separate demo dataset (SSL4EO-S12) browsable at `/satellite`. It uses the
**same key-mode pipeline** via a shared helper (`satellite/keymode.py`):

- `satellite/setup.py` — downloads Sentinel-2 scenes from STAC, AES-encrypts
  each (blob → `data/satellite/blobs/`), NLSS-splits the key, uploads the 4 key
  shares to NODE-1..4, writes `data/satellite/catalog.json`.
- `satellite/processor.py` — reconstructs an image: fetch key shares → NLSS
  recover key → AES decrypt local blob → gunzip.
- `satellite/routes.py` — `GET /api/satellite/{status,catalog}`,
  `POST /api/satellite/reconstruct/{img_id}`.

In the catalog, each image exposes:
- `essential_share` → the **local ciphertext blob** (the "essential" local piece).
- `shares` → the **4 NLSS key shares** distributed across nodes.

Maintenance scripts: `rebuild.py` (re-encrypt all raw images), `resume.py`
(continue downloading from STAC). `benchmark.py` measures the key-mode
round-trip; `benchmark_full.py` retains the legacy full-payload split for
comparison.

---

## Authentication Model

Mock Web3 wallet with three preset identities:

| Identity | Address |
|---|---|
| Researcher Alpha | `0xA1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2` |
| Analyst Beta | `0xC3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4` |
| Operator Gamma | `0xE5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6` |

`POST /api/auth/mock-wallet { address }` returns a JWT (24h). The token is kept
in `sessionStorage` (per-tab isolation). All subsequent requests carry
`Authorization: Bearer <token>`.

Reconstruction and listing are **owner-only** — there is no cross-user import.
Each wallet sees only the manifests it owns.

---

## Blockchain Anchoring

Mock anchoring only (no real chain):
- **Merkle root:** SHA-256 of the sorted key-share CIDs concatenated.
- **Transaction hash:** SHA-256 of the manifest UUID, `0x`-prefixed.

Both are stored in the manifest and shown in the UI. In production these would
be replaced with real on-chain anchoring (e.g. an EVM smart contract) to prove
the data existed at a given time.

---

## API Endpoints

| Method | Path | Auth | Description |
|---|---|:---:|---|
| `GET` | `/health` | No | Health check |
| `POST` | `/api/auth/mock-wallet` | No | Mock wallet connect → JWT |
| `POST` | `/api/thumbnail` | No | Generate base64 thumbnail |
| `POST` | `/api/upload` | Yes | Upload a file (key mode, 6-stage pipeline) |
| `GET` | `/api/upload/{upload_id}/status` | No | Poll upload status |
| `GET` | `/api/archive` | Yes | List owner's files |
| `POST` | `/api/reconstruct/{manifest_id}` | Yes | Reconstruct (owner-only) |
| `GET` | `/api/nodes` | No | Storage node health |
| `DELETE` | `/api/archive/{manifest_id}` | Yes | Delete a manifest (owner-only) |
| `GET` | `/api/satellite/status` | No | Satellite catalog readiness |
| `GET` | `/api/satellite/catalog` | No | Satellite image catalog |
| `POST` | `/api/satellite/reconstruct/{img_id}` | No | Reconstruct a satellite image |
| `GET` | `/{full_path:path}` | No | SPA catch-all |

---

## Ngrok Tunnel Setup

Only **one** tunnel is needed (free tier):

```bash
ngrok http 8000
```

The browser reaches FastAPI via the tunnel; FastAPI reaches IPFS cluster/gateway
over localhost.

---

## Project Structure

```
decentrasec/
├── README.md
├── SETUP.md
├── backend/
│   ├── main.py                 # FastAPI app, all routes
│   ├── config.py               # Env config, node names, ENCRYPTED_DATA_DIR
│   ├── auth.py                 # JWT auth, 3 mock wallets
│   ├── store.py                # Manifest JSON store (owner-scoped)
│   ├── requirements.txt
│   ├── .env.example
│   ├── crypto/
│   │   ├── aes.py              # AES-256-GCM (blob = nonce||tag||ct)
│   │   ├── dmaya.py            # NLSS (DMaya 1.7) wrapper
│   │   ├── hash.py             # SHA-256, mock merkle/tx
│   │   └── DMaya1.7/           # DMaya binaries + runtime
│   ├── ipfs/
│   │   ├── cluster.py          # Cluster API upload
│   │   ├── gateway.py          # Gateway fetch
│   │   └── node.py             # Per-node add/fetch/health
│   ├── pipelines/
│   │   ├── upload.py           # Key-mode upload pipeline
│   │   └── reconstruct.py      # Key-mode reconstruct pipeline
│   ├── satellite/
│   │   ├── keymode.py          # Shared AES+NLSS helper
│   │   ├── config.py           # Satellite dirs, 4 nodes, STAC regions
│   │   ├── setup.py            # Build catalog (STAC → key mode)
│   │   ├── processor.py        # Reconstruct satellite image
│   │   ├── routes.py           # /api/satellite/*
│   │   ├── rebuild.py          # Re-encrypt all raw images
│   │   ├── resume.py           # Continue STAC downloads
│   │   ├── benchmark.py        # Key-mode round-trip benchmark
│   │   └── benchmark_full.py   # Legacy full-payload benchmark (comparison)
│   ├── static/                 # Built React SPA
│   └── data/
│       ├── manifests.json      # Owner manifests (runtime)
│       ├── encrypted/          # AES ciphertext blobs (local)
│       └── satellite/          # raw/, blobs/, catalog.json
│
└── frontend/
    ├── package.json            # React 18, Zustand, Axios, Vite 5
    └── src/
        ├── App.jsx
        ├── api/client.js
        ├── store/useStore.js
        ├── pages/
        │   ├── Login.jsx
        │   ├── Dashboard.jsx
        │   └── SatelliteShares.jsx
        └── components/
            ├── Header.jsx
            ├── UploadPanel.jsx
            ├── PipelineStepper.jsx
            ├── NodeCards.jsx
            ├── ArchiveTable.jsx
            └── SatelliteTable.jsx
```

---

## Quick Start

See [SETUP.md](./SETUP.md) for the full guide. Summary:

```bash
# Backend
cd ~/decentrasec/backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # edit JWT_SECRET, ports
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Frontend
cd ~/decentrasec/frontend
npm install && npm run build
cp -r dist/* ../backend/static/

# (optional) Satellite dataset
cd ~/decentrasec/backend && python satellite/setup.py

# (optional) expose remotely
ngrok http 8000
```
