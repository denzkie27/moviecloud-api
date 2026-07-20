import os
from fastapi import FastAPI
from fastapi.responses import FileResponse
import uvicorn

# Import the API app from api.py
from api import app as api_app

# Create main app
app = FastAPI()

# Include all API routes from api_app directly (no mount)
app.include_router(api_app.router)

# Now add HTML page routes (they will not conflict because API doesn't have these paths)
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
