# DecentraSec — Setup Guide

## Prerequisites

- Linux machine (your bootstrap/owner node: `192.168.22.95`)
- IPFS daemon + IPFS cluster running (cluster API `:9094`, gateway `:8080`)
- Cluster auth: `admin:Agni@123`
- **`mono` runtime** — required to run the NLSS (DMaya 1.7) binaries
  (`DMaya1.7-enc` / `DMaya1.7-dec`). Install with:
  ```bash
  sudo apt install -y mono-complete
  ```
- Python 3.10+
- Node.js 18+
- (Optional) ngrok if accessing from outside the LAN

---

## Step 1: Copy Project to Server

```bash
scp -r decentrasec/ crrao@192.168.22.95:~/decentrasec/
```

Or clone from git if you've pushed it.

---

## Step 2: Backend Setup

```bash
cd ~/decentrasec/backend

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
```

### Edit `.env`

```bash
nano .env
```

```env
IPFS_CLUSTER_API=http://localhost:9094
IPFS_GATEWAY=http://localhost:8080
IPFS_CLUSTER_USER=admin
IPFS_CLUSTER_PASS=Agni@123

# Generate: python3 -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET=paste-your-random-hex-here

CORS_ORIGINS=http://localhost:5173,http://192.168.22.95:5173

MANIFESTS_FILE=./data/manifests.json
ENCRYPTED_DATA_DIR=./data/encrypted
DEMO_DATA_DIR=./data/demo-data
MAX_FILE_SIZE_MB=500
IPFS_UPLOAD_TIMEOUT=300
IPFS_FETCH_TIMEOUT=120
```

### Verify IPFS + mono

```bash
# Cluster API
curl -u admin:'Agni@123' http://localhost:9094/id

# Gateway
curl http://localhost:8080/ipfs/QmSomeHash

# mono (NLSS binaries)
mono --version
```

If the gateway returns a redirect, disable subdomain mode:

```bash
ipfs config Gateway.UseSubdomains false
pkill -f "ipfs daemon"
ipfs daemon &
```

---

## Step 3: Frontend Setup

```bash
cd ~/decentrasec/frontend
npm install
```

### Frontend `.env`

```bash
cat > .env << 'EOF'
VITE_API_BASE=http://192.168.22.95:8000
EOF
```

Use `http://localhost:8000` if accessing from the same machine.

### Build for production (served by FastAPI)

```bash
npm run build
cp -r dist/ ../backend/static/
```

---

## Step 4: (Optional) Build the Satellite Dataset

The satellite module downloads Sentinel-2 scenes from STAC and runs them
through the same key-mode pipeline (AES blob local, NLSS key shares to nodes).

```bash
cd ~/decentrasec/backend
source venv/bin/activate

# Downloads images, AES-encrypts, NLSS-splits keys, uploads key shares, writes catalog
python satellite/setup.py

# Force regenerate an existing catalog
python satellite/setup.py --force

# Re-encrypt only from raw images already on disk (no STAC download)
python satellite/rebuild.py

# Continue downloading more scenes from STAC
python satellite/resume.py --start 32
```

Outputs go to `data/satellite/` (`raw/`, `blobs/`, `catalog.json`).

---

## Step 5: Start Everything

### Terminal 1 — FastAPI Backend

```bash
cd ~/decentrasec/backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Terminal 2 — React Dev Server (optional, for development)

```bash
cd ~/decentrasec/frontend
npm run dev
```

### (Optional) Terminal 3 — Ngrok

```bash
ngrok http 8000
```

Add the ngrok URL to `CORS_ORIGINS` in `backend/.env` and restart FastAPI.

---

## Step 6: Access the Demo

| From | URL |
|---|---|
| Same machine (bootstrap node) | `http://localhost:5173` (dev) or `http://localhost:8000` (built) |
| Another machine on LAN | `http://192.168.22.95:8000` |
| Via ngrok (any network) | `https://xxxx.ngrok-free.app` |

---

## Step 7: Verify Everything Works

### 1. Health check

```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0","manifests_count":0}
```

### 2. Auth test

```bash
curl -X POST http://localhost:8000/api/auth/mock-wallet \
  -H "Content-Type: application/json" \
  -d '{"address":"0xA1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2"}'
# returns a JWT token
```

### 3. Upload test (key mode — file only, no scheme params)

```bash
echo "test satellite data" > /tmp/test.tif

TOKEN=$(curl -s -X POST http://localhost:8000/api/auth/mock-wallet \
  -H "Content-Type: application/json" \
  -d '{"address":"0xA1B2C3D4E5F6A1B2C3D4E5F6A1B2C3D4E5F6A1B2"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

UPLOAD_ID=$(curl -s -X POST http://localhost:8000/api/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/tmp/test.tif" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# Poll until stage == "done"
curl -s http://localhost:8000/api/upload/$UPLOAD_ID/status \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# List archive (owner only)
curl http://localhost:8000/api/archive \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

The pipeline stages are: `validate → compress → encrypt → split → distribute → anchor`.

### 4. Open browser

Navigate to `http://192.168.22.95:8000`, pick a wallet, upload a file, then
click **Reconstruct** to download the decrypted original.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: Crypto` | `pip install pycryptodome` |
| NLSS/DMaya errors / `mono: not found` | `sudo apt install -y mono-complete` (needed to run `DMaya1.7-enc/-dec`) |
| `DMaya binary not found` | Ensure `backend/crypto/DMaya1.7/` contains `DMaya1.7-enc` + `DMaya1.7-dec` (chmod +x on Linux) |
| Cluster API returns 401 | Check `IPFS_CLUSTER_USER` / `IPFS_CLUSTER_PASS` in `.env` |
| Gateway returns redirect | `ipfs config Gateway.UseSubdomains false`, restart daemon |
| CORS error in browser | Add the frontend URL to `CORS_ORIGINS` and restart backend |
| Upload hangs at "distribute" | Storage node unreachable; check `GET /api/nodes` and node IPFS daemons |
| Reconstruct fails: blob not found | The ciphertext blob (`data/encrypted/<id>.bin`) was deleted; without it the file is unrecoverable |
| Reconstruct fails: key shares | One or more NLSS key-share nodes offline; the decoder needs all 4 shares |
| Frontend shows blank | Check browser console; ensure `VITE_API_BASE` points to the backend |
| ngrok warning page | Click "Visit Site" or send `Ngrok-Skip-Browser-Warning` header |

---

## Reset Demo

```bash
# Clear owner manifests + local ciphertext blobs
rm -f ~/decentrasec/backend/data/manifests.json
rm -rf ~/decentrasec/backend/data/encrypted

# Rebuild the satellite catalog from raw images
cd ~/decentrasec/backend && source venv/bin/activate
python satellite/rebuild.py
```

---

## Notes on the Personal-Vault Model

- **Ciphertext blobs live on the owner node** (`data/encrypted/`). If the owner
  loses the blob, the file is unrecoverable even if all key shares survive on
  IPFS — keep backups of `data/encrypted/`.
- **Manifests are local** (`data/manifests.json`); they are not on IPFS.
- **No cross-user sharing** — each wallet sees and reconstructs only its own
  files. There is no manifest-CID import feature.
- **IPFS holds only the NLSS key shares** (a few ~tens of bytes per file per
  node); the bulk data never goes to IPFS.

---

## Project Structure

```
decentrasec/
├── README.md
├── SETUP.md
├── backend/
│   ├── main.py              # FastAPI app, all routes
│   ├── config.py            # Env config + ENCRYPTED_DATA_DIR
│   ├── auth.py              # JWT auth + mock wallets
│   ├── store.py             # Manifest JSON store (owner-scoped)
│   ├── crypto/
│   │   ├── aes.py           # AES-256-GCM (blob = nonce||tag||ct)
│   │   ├── dmaya.py         # NLSS (DMaya 1.7) wrapper
│   │   ├── hash.py          # SHA-256, mock merkle/tx
│   │   └── DMaya1.7/        # NLSS binaries + runtime
│   ├── ipfs/
│   │   ├── cluster.py       # Cluster API upload
│   │   ├── gateway.py       # Gateway fetch
│   │   └── node.py          # Per-node add/fetch/health
│   ├── pipelines/
│   │   ├── upload.py        # Key-mode upload pipeline
│   │   └── reconstruct.py   # Key-mode reconstruct pipeline
│   ├── satellite/
│   │   ├── keymode.py       # Shared AES+NLSS helper
│   │   ├── config.py
│   │   ├── setup.py         # Build catalog (STAC → key mode)
│   │   ├── processor.py     # Reconstruct satellite image
│   │   ├── routes.py        # /api/satellite/*
│   │   ├── rebuild.py
│   │   ├── resume.py
│   │   ├── benchmark.py     # Key-mode benchmark
│   │   └── benchmark_full.py
│   ├── requirements.txt
│   ├── .env.example
│   └── data/
│       ├── manifests.json   # Owner manifests (runtime)
│       ├── encrypted/       # AES ciphertext blobs (local)
│       └── satellite/       # raw/, blobs/, catalog.json
│
└── frontend/
    ├── package.json
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
