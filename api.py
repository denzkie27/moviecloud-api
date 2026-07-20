import re, json, httpx, logging
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MovieBox API Pro", version="2.1.11")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

API_BASE = "https://h5-api.aoneroom.com/wefeed-h5api-bff"
_bearer_token = None

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Referer": "https://moviebox.ph/",
    "Origin": "https://moviebox.ph",
    "Accept": "application/json",
    "Content-Type": "application/json",
}

PLAYER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
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
    """Try multiple methods to get stream data"""
    
    # Method 1: Get domain from API, then fetch stream
    try:
        dom = await _req(f"{API_BASE}/media-player/get-domain")
        domain = dom.get("data", "").rstrip("/") or "https://netfilm.world"
        
        headers = {
            **PLAYER_HEADERS,
            "Origin": domain,
            "Referer": f"{domain}/",
        }
        
        ref = f"{domain}/spa/videoPlayPage/movies/{slug}?id={sid}&type=/movie/detail&detailSe={se}&detailEp={ep}&lang=en"
        url = f"{domain}/wefeed-h5api-bff/subject/play?subjectId={sid}&se={se}&ep={ep}&detailPath={slug}"
        
        logger.info(f"Method 1: Trying {domain}")
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
            r = await c.get(url, headers={**headers, "Referer": ref})
            data = r.json().get("data", {})
            if data.get("hasResource") and data.get("streams"):
                logger.info(f"Method 1 SUCCESS: {len(data['streams'])} streams")
                return data, ref
            else:
                logger.warning(f"Method 1: has_resource={data.get('hasResource')}, streams={len(data.get('streams', []))}")
    except Exception as e:
        logger.error(f"Method 1 failed: {e}")
    
    # Method 2: Try netfilm.world directly
    try:
        domain = "https://netfilm.world"
        headers = {
            **PLAYER_HEADERS,
            "Origin": domain,
            "Referer": domain,
        }
        ref = f"{domain}/spa/videoPlayPage/movies/{slug}?id={sid}&type=/movie/detail&detailSe={se}&detailEp={ep}&lang=en"
        url = f"{domain}/wefeed-h5api-bff/subject/play?subjectId={sid}&se={se}&ep={ep}&detailPath={slug}"
        
        logger.info(f"Method 2: Trying {domain}")
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
            r = await c.get(url, headers={**headers, "Referer": ref})
            data = r.json().get("data", {})
            if data.get("hasResource") and data.get("streams"):
                logger.info(f"Method 2 SUCCESS: {len(data['streams'])} streams")
                return data, ref
            else:
                logger.warning(f"Method 2: has_resource={data.get('hasResource')}, streams={len(data.get('streams', []))}")
    except Exception as e:
        logger.error(f"Method 2 failed: {e}")
    
    # Method 3: Try moviebox.ph domain
    try:
        domain = "https://moviebox.ph"
        headers = {
            **PLAYER_HEADERS,
            "Origin": domain,
            "Referer": domain,
        }
        ref = f"{domain}/spa/videoPlayPage/movies/{slug}?id={sid}&type=/movie/detail&detailSe={se}&detailEp={ep}&lang=en"
        url = f"https://h5-api.aoneroom.com/wefeed-h5api-bff/subject/play?subjectId={sid}&se={se}&ep={ep}&detailPath={slug}"
        
        logger.info(f"Method 3: Trying {domain}")
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
            r = await c.get(url, headers={**headers, "Referer": ref})
            data = r.json().get("data", {})
            if data.get("hasResource") and data.get("streams"):
                logger.info(f"Method 3 SUCCESS: {len(data['streams'])} streams")
                return data, ref
            else:
                logger.warning(f"Method 3: has_resource={data.get('hasResource')}, streams={len(data.get('streams', []))}")
    except Exception as e:
        logger.error(f"Method 3 failed: {e}")
    
    # Method 4: Try with se=1,ep=1 (sometimes needed for movies)
    if se == 0 and ep == 0:
        try:
            domain = "https://netfilm.world"
            headers = {
                **PLAYER_HEADERS,
                "Origin": domain,
                "Referer": domain,
            }
            ref = f"{domain}/spa/videoPlayPage/movies/{slug}?id={sid}&type=/movie/detail&detailSe=1&detailEp=1&lang=en"
            url = f"{domain}/wefeed-h5api-bff/subject/play?subjectId={sid}&se=1&ep=1&detailPath={slug}"
            
            logger.info(f"Method 4: Trying se=1,ep=1")
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
                r = await c.get(url, headers={**headers, "Referer": ref})
                data = r.json().get("data", {})
                if data.get("hasResource") and data.get("streams"):
                    logger.info(f"Method 4 SUCCESS: {len(data['streams'])} streams")
                    return data, ref
        except Exception as e:
            logger.error(f"Method 4 failed: {e}")
    
    logger.error("ALL METHODS FAILED - No streams available")
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
    try:
        data, ref = await _get_stream_data(sid, detail_path, se, ep)
        streams = data.get("streams", [])
        
        # Also check DASH if MP4 not available
        dash_sources = data.get("dash", [])
        
        # If no MP4 streams but DASH available, try DASH
        if not streams and dash_sources:
            # Return DASH manifest directly
            dash_url = dash_sources[0].get("url")
            if dash_url:
                async def gen_dash():
                    async with httpx.AsyncClient(follow_redirects=True, timeout=300) as c:
                        async with c.stream("GET", dash_url, headers={**PLAYER_HEADERS, "Referer": ref}) as r2:
                            async for chunk in r2.aiter_bytes(1048576):
                                yield chunk
                return StreamingResponse(gen_dash(), media_type="application/dash+xml")
        
        if not streams:
            raise HTTPException(404, f"No streams available. has_resource: {data.get('hasResource')}")
        
        q = quality.replace("p", "")
        sel = next((s for s in streams if s.get("resolutions") == q), streams[-1])
        
        if not sel.get("url"):
            raise HTTPException(404, "No stream URL found")
        
        logger.info(f"Streaming: {sel.get('resolution')} from {sel.get('url')[:80]}...")
        
        async def gen():
            async with httpx.AsyncClient(follow_redirects=True, timeout=300, verify=False) as c:
                stream_headers = {
                    **PLAYER_HEADERS,
                    "Referer": ref,
                    "Origin": "https://netfilm.world",
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
                }
                async with c.stream("GET", sel["url"], headers=stream_headers) as r2:
                    logger.info(f"CDN response: {r2.status_code}")
                    if r2.status_code != 200:
                        raise HTTPException(502, f"CDN returned {r2.status_code}")
                    async for chunk in r2.aiter_bytes(1048576):
                        yield chunk
        
        return StreamingResponse(gen(), media_type="video/mp4")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stream proxy error: {e}")
        raise HTTPException(500, str(e))

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
