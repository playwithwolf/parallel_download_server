from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import json
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
ORIGINAL_FILE = BASE_DIR / "file.jkpg"
CHUNKS_DIR = BASE_DIR / "file.jkpg_chunks"
MERGE_DIR = BASE_DIR / "file.jkpg_merge"
MERGE_FILE = MERGE_DIR / "file.jkpg"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/file")
def download_file():
    if not ORIGINAL_FILE.exists():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(str(ORIGINAL_FILE), media_type="application/octet-stream", filename=ORIGINAL_FILE.name)

@app.get("/merge/file")
def download_merged_file():
    if not MERGE_FILE.exists():
        raise HTTPException(status_code=404, detail="merged file not found")
    return FileResponse(str(MERGE_FILE), media_type="application/octet-stream", filename=MERGE_FILE.name)

@app.get("/chunks/manifest")
def chunks_manifest():
    manifest_path = CHUNKS_DIR / "manifest.json"
    if not manifest_path.exists():
        raise HTTPException(status_code=404, detail="manifest not found")
    with open(manifest_path, "r", encoding="utf-8") as m:
        data = json.load(m)
    return JSONResponse(content=data)

@app.get("/chunks/list")
def chunks_list(offset: int = Query(0, ge=0), limit: int = Query(1000, gt=0)):
    if not CHUNKS_DIR.exists():
        raise HTTPException(status_code=404, detail="chunks dir not found")
    files = sorted([p.name for p in CHUNKS_DIR.glob("chunk_*.part")])
    end = min(len(files), offset + limit)
    return {"chunks": files[offset:end], "total": len(files), "offset": offset, "limit": limit}

@app.get("/chunks/{name}")
def chunk(name: str, request: Request, response: Response):
    path = CHUNKS_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="chunk not found")
    manifest_path = CHUNKS_DIR / "manifest.json"
    etag = None
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as m:
            data = json.load(m)
            for item in data.get("chunks", []):
                if item.get("name") == name:
                    etag = item.get("sha256")
                    break
    inm = request.headers.get("if-none-match")
    if etag and inm == etag:
        response.status_code = 304
        return Response()
    headers = {}
    if etag:
        headers["ETag"] = etag
    try:
        stat = path.stat()
        headers["Last-Modified"] = time.strftime("%a, %d %b %Y %H:%M:%S GMT", time.gmtime(stat.st_mtime))
    except Exception:
        pass
    headers["Cache-Control"] = "public, max-age=3600"
    return FileResponse(str(path), media_type="application/octet-stream", filename=path.name, headers=headers)

