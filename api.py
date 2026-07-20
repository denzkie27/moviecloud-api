import re, json, httpx, logging
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MovieBox API Pro", version="2.1.10")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

API_BASE = "https://h5-api.aoneroom.com/wefeed-h5api-bff"
_bearer_token = None

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Referer": "https://moviebox.ph/",
    "Origin": "https://moviebox.ph",
    "Accept": "application/json",
    "Content-Type": "application/json",
    "X-Forwarded-For": "112.198.0.0",
    "CF-IPCountry": "PH",
}

PLAYER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://netfilm.world",
    "Referer": "https://netfilm.world/",
    "X-Forwarded-For": "112.198.0.0",
}

async def _get_token():
    global _bearer_token
    if _bearer_token:
        return _bearer_token
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
            r = await c.get(f"{API_BASE}/home?host=moviebox.ph", headers=DEFAULT_HEADERS)
            x_user = r.headers.get("x-user")
            if x_user:
                _bearer_token = json.loads(x_user).get("token")
            if not _bearer_token:
                m = re.search(r"token=([^;]+)", r.headers.get("set-cookie", ""))
                if m:
                    _bearer_token = m.group(1)
        logger.info("Bearer token obtained")
    except Exception as e:
        logger.error(f"Token error: {e}")
    return _bearer_token or ""

async def _req(url, method="GET", payload=None):
    token = await _get_token()
    headers = {**DEFAULT_HEADERS, "Authorization": f"Bearer {token}" if token else ""}
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
        if method == "POST":
            r = await c.post(url, headers=headers, json=payload)
        else:
            r = await c.get(url, headers=headers)
        if r.status_code != 200:
            logger.error(f"Upstream error: {r.status_code} for {url}")
            raise HTTPException(502, f"Upstream error: {r.status_code}")
        return r.json()

async def _get_stream_data(sid, slug, se=0, ep=0):
    """Try multiple domains to get stream data"""
    domains_to_try = []
    
    # Try to get domain from API first
    try:
        dom = await _req(f"{API_BASE}/media-player/get-domain")
        domain = dom.get("data", "").rstrip("/")
        if domain:
            domains_to_try.append(domain)
    except Exception as e:
        logger.error(f"Domain fetch error: {e}")
    
    # Add fallback domains
    domains_to_try.extend([
        "https://netfilm.world",
        "https://www.netfilm.world",
        "https://moviebox.ph"
    ])
    
    # Remove duplicates
    domains_to_try = list(dict.fromkeys(domains_to_try))
    
    for domain in domains_to_try:
        try:
            ref = f"{domain}/spa/videoPlayPage/movies/{slug}?id={sid}&type=/movie/detail&detailSe={se}&detailEp={ep}&lang=en"
            url = f"{domain}/wefeed-h5api-bff/subject/play?subjectId={sid}&se={se}&ep={ep}&detailPath={slug}"
            
            logger.info(f"Trying stream domain: {domain}")
            
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
                r = await c.get(url, headers={**PLAYER_HEADERS, "Referer": ref})
                data = r.json().get("data", {})
                
                if data.get("hasResource") and data.get("streams"):
                    logger.info(f"✅ Stream found on {domain} - {len(data['streams'])} sources")
                    return data, ref
                else:
                    logger.warning(f"❌ No stream on {domain}")
        except Exception as e:
            logger.error(f"Failed on {domain}: {e}")
            continue
    
    logger.error("All domains failed, returning empty data")
    return {"hasResource": False, "streams": [], "dash": []}, ""

# ===== HTML PAGES =====
@app.get("/movie.html")
async def movie_page():
    return FileResponse("movie.html")

@app.get("/tvshow.html")
async def tvshow_page():
    return FileResponse("tvshow.html")

@app.get("/streaming.html")
async def streaming_page():
    return FileResponse("streaming.html")

@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return FileResponse("streaming.html")

# ===== STREAM PROXY =====
@app.get("/stream-proxy/{sid}")
async def stream_proxy(sid: str, detail_path: str, quality: str = "480p", se: int = 0, ep: int = 0):
    data, ref = await _get_stream_data(sid, detail_path, se, ep)
    streams = data.get("streams", [])
    if not streams:
        raise HTTPException(404, "No streams available")
    q = quality.replace("p", "")
    sel = next((s for s in streams if s.get("resolutions") == q), streams[-1])
    if not sel.get("url"):
        raise HTTPException(404, "No stream URL")
    async def gen():
        async with httpx.AsyncClient(follow_redirects=True, timeout=300) as c:
            async with c.stream("GET", sel["url"], headers={**PLAYER_HEADERS, "Referer": ref}) as r2:
                async for chunk in r2.aiter_bytes(1048576):
                    yield chunk
    return StreamingResponse(gen(), media_type="video/mp4")

# ===== DOWNLOAD =====
@app.get("/download/{sid}")
async def download(sid: str, detail_path: str, quality: str = "480p", se: int = 0, ep: int = 0):
    data, ref = await _get_stream_data(sid, detail_path, se, ep)
    streams = data.get("streams", [])
    if not streams:
        raise HTTPException(404, "No streams available")
    q = quality.replace("p", "")
    sel = next((s for s in streams if s.get("resolutions") == q), streams[-1])
    async def gen():
        async with httpx.AsyncClient(follow_redirects=True, timeout=300) as c:
            async with c.stream("GET", sel["url"], headers={**PLAYER_HEADERS, "Referer": ref}) as r2:
                async for chunk in r2.aiter_bytes(1048576):
                    yield chunk
    fn = detail_path.replace("-", " ").title()
    if se > 0:
        fn += f"_S{se}E{ep}"
    fn += f"_{quality}.mp4"
    return StreamingResponse(gen(), media_type="video/mp4", headers={"Content-Disposition": f'attachment; filename="{fn}"'})

# ===== EPISODES =====
@app.get("/api/episodes/{sid}")
async def episodes(sid: str, detail_path: str):
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
            eps = [{"season": 1, "episode": i, "title": f"Episode {i}"} for i in range(1, 21)]
        return {
            "subject_id": sid,
            "detail_path": detail_path,
            "total": len(eps),
            "episodes": eps[:100]
        }
    except Exception as e:
        raise HTTPException(500, str(e))

# ===== HOME API =====
@app.get("/home")
async def home():
    data = await _req(f"{API_BASE}/home?host=moviebox.ph")
    sections = []
    for op in (data.get("data", {}).get("operatingList") or []):
        t = op.get("type")
        title = op.get("title", "Featured")
        if t == "BANNER":
            items = [{
                "name": i.get("title") or (i.get("subject") or {}).get("title"),
                "poster_url": i.get("image", {}).get("url") or (i.get("subject") or {}).get("cover", {}).get("url"),
                "slug": i.get("detailPath") or (i.get("subject") or {}).get("detailPath"),
                "subject_id": (i.get("subject") or {}).get("subjectId")
            } for i in op.get("banner", {}).get("items", []) if i.get("title")]
            sections.append({"section": "Banner", "items": items})
        elif t in ["SUBJECTS_MOVIE", "SUBJECTS_TV", "SUBJECTS_ANIMATION"]:
            items = [{
                "name": s.get("title"),
                "poster_url": s.get("cover", {}).get("url"),
                "slug": s.get("detailPath"),
                "subject_id": s.get("subjectId"),
                "badge": s.get("corner"),
                "rating": s.get("imdbRatingValue")
            } for s in op.get("subjects", [])]
            sections.append({"section": title, "items": items})
    return {"status": "success", "sections": sections}

# ===== CATEGORIES =====
async def _cat(tab, page=1):
    data = await _req(f"{API_BASE}/subject/filter", "POST", {
        "tabId": tab,
        "filter": {"sort": "RECOMMEND", "genre": "ALL", "country": "ALL", "year": "ALL", "language": "ALL"},
        "page": page,
        "perPage": 24
    })
    inner = data.get("data", {})
    raw = inner.get("items") or inner.get("subjects") or []
    items = [{
        "name": s.get("title"),
        "poster_url": s.get("cover", {}).get("url"),
        "slug": s.get("detailPath"),
        "subject_id": s.get("subjectId"),
        "badge": s.get("corner"),
        "year": (s.get("releaseDate") or "")[:4] if s.get("releaseDate") else None
    } for s in raw]
    return {"page": page, "items": items}

@app.get("/movies")
async def movies(page: int = 1):
    return await _cat(2, page)

@app.get("/tv-series")
async def tv_series(page: int = 1):
    return await _cat(5, page)

@app.get("/animation")
async def animation(page: int = 1):
    return await _cat(8, page)

# ===== SEARCH =====
@app.get("/search")
async def search(q: str = Query(default="", min_length=1), page: int = 1):
    data = await _req(f"{API_BASE}/subject/search", "POST", {
        "keyword": q, "page": page, "perPage": 20
    })
    inner = data.get("data", {})
    raw = inner.get("items") or inner.get("list") or []
    items = [{
        "name": s.get("title"),
        "poster_url": s.get("cover", {}).get("url"),
        "slug": s.get("detailPath"),
        "subject_id": s.get("subjectId")
    } for s in raw]
    return {"query": q, "page": page, "items": items}

# ===== STREAM INFO =====
@app.get("/api/stream/{sid}")
async def stream_info(sid: str, detail_path: str, se: int = 0, ep: int = 0):
    data, _ = await _get_stream_data(sid, detail_path, se, ep)
    streams = [{
        "resolution": f"{s.get('resolutions')}p",
        "url": s.get("url"),
        "size": s.get("size"),
        "duration": s.get("duration")
    } for s in data.get("streams", [])]
    return {
        "subject_id": sid,
        "se": se,
        "ep": ep,
        "has_resource": data.get("hasResource", False),
        "sources": streams,
        "dash": data.get("dash", []),
        "free_episodes": data.get("freeNum"),
        "note": None if data.get("hasResource") else "No stream found."
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
