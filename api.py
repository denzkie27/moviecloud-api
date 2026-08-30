import re, json, httpx, logging, time
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, RedirectResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MovieBox API Pro", version="2.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

API_BASE = "https://h5-api.aoneroom.com/wefeed-h5api-bff"
_bearer_token = None
_stream_cache = {}
CACHE_TTL = 15

DEFAULT_HEADERS = { ... }  # keep as before
PLAYER_HEADERS = { ... }   # keep as before

async def _get_token(): ...  # unchanged
async def _req(url, method="GET", payload=None): ...  # unchanged
async def _get_stream_data(sid, slug, se=0, ep=0): ...  # unchanged

# Helper to get episodes list (shared by endpoints)
async def _get_episodes_list(sid: str, detail_path: str):
    try:
        d = await _req(f"{API_BASE}/detail?detailPath={detail_path}")
        inner = d.get("data", {})
        seasons = inner.get("seasons") or inner.get("seasonList") or []
        eps = []
        for sn in seasons:
            snum = sn.get("se") or sn.get("seasonNumber") or 0
            for ep in (sn.get("episodes") or sn.get("eps") or []):
                eps.append({
                    "season": int(snum),
                    "episode": int(ep.get("ep") or ep.get("episodeNumber") or 0),
                    "title": ep.get("title", f"Episode {ep.get('ep', '?')}")
                })
        if not eps:
            # fallback: if no seasons found but maybe episodes are direct?
            eps = []
        return eps
    except Exception as e:
        logger.error(f"Error fetching episodes for {sid}: {e}")
        return []

# ===== HTML PAGES =====
@app.get("/movie.html") ...
@app.get("/tvshow.html") ...
@app.get("/streaming.html") ...
@app.get("/home.html") ...
@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return FileResponse("home.html")

@app.get("/health") ...

# ===== STREAM PROXY =====
# (unchanged from before)

# ===== DOWNLOAD =====
# (unchanged)

# ===== EPISODES ENDPOINT =====
@app.get("/api/episodes/{sid}")
async def episodes(sid: str, detail_path: str):
    eps = await _get_episodes_list(sid, detail_path)
    if eps:
        return {"subject_id": sid, "detail_path": detail_path, "total": len(eps), "episodes": eps[:100]}
    else:
        return {"subject_id": sid, "detail_path": detail_path, "total": 0, "episodes": []}

# ===== HOME API =====
# (unchanged)

# ===== CATEGORIES =====
# (unchanged)

# ===== SEARCH =====
# (unchanged)

# ===== STREAM INFO =====
@app.get("/api/stream/{sid}")
async def stream_info(sid: str, detail_path: str, se: int = 0, ep: int = 0):
    data, _, _ = await _get_stream_data(sid, detail_path, se, ep)

    # Prepare streams and dash
    streams = [ ... ]  # same as before
    dash = [ ... ]      # same as before

    has_resource = data.get("hasResource", False)
    is_series = False

    # If no streams at se=0,ep=0 and might be a series, check episodes
    if not has_resource and se == 0 and ep == 0:
        eps = await _get_episodes_list(sid, detail_path)
        if eps:
            is_series = True

    return {
        "subject_id": sid,
        "se": se,
        "ep": ep,
        "has_resource": has_resource,
        "sources": streams,
        "dash": dash,
        "free_episodes": data.get("freeNum"),
        "is_series": is_series,
        "note": None if has_resource else ("TV series detected" if is_series else "No stream found.")
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
