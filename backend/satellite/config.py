import os
from pathlib import Path

_BASE_DIR = Path(__file__).parent.parent / "data" / "satellite"
RAW_DIR = _BASE_DIR / "raw"
THUMB_DIR = _BASE_DIR / "thumbnails"
SHARES_DIR = _BASE_DIR / "shares"
BLOB_DIR = _BASE_DIR / "blobs"
CATALOG_FILE = _BASE_DIR / "catalog.json"

N_IMAGES = 100
SEED = 42

SENSORS = ["S1-SAR", "S2-MSI", "S2-RGB", "S2-NIR"]
SEASONS = ["spring", "summer", "autumn", "winter"]
RESOLUTIONS = {"S1-SAR": 10, "S2-MSI": 10, "S2-RGB": 10, "S2-NIR": 20}

NODE_NAMES = ["NODE-1", "NODE-2", "NODE-3", "NODE-4"]
NODE_IPS = {
    "NODE-1": "192.168.22.90",
    "NODE-2": "192.168.22.91",
    "NODE-3": "192.168.22.92",
    "NODE-4": "192.168.22.93",
}

STAC_URL = "https://earth-search.aws.element84.com/v1/search"

STAC_REGIONS = [
    {"bbox": [5, 47, 8, 50], "months": "2023-03-01T00:00:00Z/2023-05-31T23:59:59Z", "sensor": "S2-RGB", "season": "spring"},
    {"bbox": [10, 45, 13, 48], "months": "2023-06-01T00:00:00Z/2023-08-31T23:59:59Z", "sensor": "S2-MSI", "season": "summer"},
    {"bbox": [20, 40, 23, 43], "months": "2023-09-01T00:00:00Z/2023-11-30T23:59:59Z", "sensor": "S2-NIR", "season": "autumn"},
    {"bbox": [-5, 50, -2, 53], "months": "2023-12-01T00:00:00Z/2024-02-28T23:59:59Z", "sensor": "S1-SAR", "season": "winter"},
    {"bbox": [-100, 35, -97, 38], "months": "2023-03-01T00:00:00Z/2023-05-31T23:59:59Z", "sensor": "S2-RGB", "season": "spring"},
    {"bbox": [-80, 38, -77, 41], "months": "2023-06-01T00:00:00Z/2023-08-31T23:59:59Z", "sensor": "S2-MSI", "season": "summer"},
    {"bbox": [-120, 45, -117, 48], "months": "2023-09-01T00:00:00Z/2023-11-30T23:59:59Z", "sensor": "S2-NIR", "season": "autumn"},
    {"bbox": [-90, 55, -87, 58], "months": "2023-12-01T00:00:00Z/2024-02-28T23:59:59Z", "sensor": "S1-SAR", "season": "winter"},
    {"bbox": [-50, -20, -47, -17], "months": "2023-03-01T00:00:00Z/2023-05-31T23:59:59Z", "sensor": "S2-RGB", "season": "spring"},
    {"bbox": [-70, -35, -67, -32], "months": "2023-06-01T00:00:00Z/2023-08-31T23:59:59Z", "sensor": "S2-MSI", "season": "summer"},
    {"bbox": [30, 0, 33, 3], "months": "2023-09-01T00:00:00Z/2023-11-30T23:59:59Z", "sensor": "S2-NIR", "season": "autumn"},
    {"bbox": [10, 30, 13, 33], "months": "2023-12-01T00:00:00Z/2024-02-28T23:59:59Z", "sensor": "S1-SAR", "season": "winter"},
    {"bbox": [100, 20, 103, 23], "months": "2023-03-01T00:00:00Z/2023-05-31T23:59:59Z", "sensor": "S2-RGB", "season": "spring"},
    {"bbox": [120, 30, 123, 33], "months": "2023-06-01T00:00:00Z/2023-08-31T23:59:59Z", "sensor": "S2-MSI", "season": "summer"},
    {"bbox": [135, 35, 138, 38], "months": "2023-09-01T00:00:00Z/2023-11-30T23:59:59Z", "sensor": "S2-NIR", "season": "autumn"},
    {"bbox": [145, -38, 148, -35], "months": "2023-12-01T00:00:00Z/2024-02-28T23:59:59Z", "sensor": "S1-SAR", "season": "winter"},
    {"bbox": [75, 25, 78, 28], "months": "2023-03-01T00:00:00Z/2023-05-31T23:59:59Z", "sensor": "S2-MSI", "season": "spring"},
    {"bbox": [115, -25, 118, -22], "months": "2023-06-01T00:00:00Z/2023-08-31T23:59:59Z", "sensor": "S2-RGB", "season": "summer"},
    {"bbox": [45, 55, 48, 58], "months": "2023-09-01T00:00:00Z/2023-11-30T23:59:59Z", "sensor": "S2-NIR", "season": "autumn"},
    {"bbox": [150, -30, 153, -27], "months": "2023-12-01T00:00:00Z/2024-02-28T23:59:59Z", "sensor": "S1-SAR", "season": "winter"},
]

STAC_PAGE_SIZE = 6
