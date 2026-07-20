import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

# Import your existing API app
from api import app as api_app

# Create a main app
app = FastAPI()

# Mount the API routes under /api (optional; you can also include them directly)
# We'll just mount the whole api_app at root
app.mount("/", api_app)

# Serve static HTML files
# We'll use a simple route for each HTML page
@app.get("/streaming.html")
async def streaming():
    return FileResponse("streaming.html")

@app.get("/movie.html")
async def movie():
    return FileResponse("movie.html")

@app.get("/tvshow.html")
async def tvshow():
    return FileResponse("tvshow.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
