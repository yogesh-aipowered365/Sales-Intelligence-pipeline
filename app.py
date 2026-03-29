from config import load_config
from extractor import extract_sales_brief
from crawler import crawl_company
from agent_search import search_company_options
import uvicorn
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi import FastAPI
import sys
import os
import json
import logging

from dotenv import load_dotenv

# Load .env from the same folder as app.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


# Suppress noisy crawl4ai logs in the web server context
logging.getLogger("crawl4ai").setLevel(logging.WARNING)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

logger = logging.getLogger(__name__)

app = FastAPI(title="Sales Intelligence Pipeline")


@app.on_event("startup")
async def startup_event():
    logger.info("Application starting up...")

    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        logger.info(".env file found at: %s", env_file)
    else:
        logger.warning(".env file NOT found at: %s", env_file)

    # Log only whether variables exist, never print secrets
    expected_vars = [
        "AZURE_FOUNDRY_API_KEY",
        "AZURE_FOUNDRY_ENDPOINT",
        "AZURE_FOUNDRY_DEPLOYMENT",
        "AZURE_FOUNDRY_API_VERSION",
    ]

    for var in expected_vars:
        logger.info("ENV %s loaded: %s", var,
                    "YES" if os.getenv(var) else "NO")


@app.get("/", response_class=HTMLResponse)
async def index():
    template_path = os.path.join(BASE_DIR, "templates", "index.html")
    with open(template_path, encoding="utf-8") as f:
        return HTMLResponse(f.read())


class SearchRequest(BaseModel):
    query: str


@app.post("/api/search")
async def search(body: SearchRequest):
    try:
        logger.info("Search request received for query: %s", body.query)
        options = search_company_options(body.query)
        return {"options": options}
    except Exception as e:
        logger.exception("Error in /api/search")
        return {"error": str(e), "options": []}


@app.get("/api/brief")
async def brief_stream(url: str):
    async def generate():
        try:
            yield f"data: {json.dumps({'type': 'progress', 'step': 'crawl', 'message': 'Starting web crawl...'})}\n\n"

            markdown, crawled_urls = await crawl_company(url)

            yield f"data: {json.dumps({'type': 'progress', 'step': 'crawl_done', 'message': f'Crawled {len(crawled_urls)} pages successfully.'})}\n\n"
            yield f"data: {json.dumps({'type': 'progress', 'step': 'extract', 'message': 'Analysing content with Azure AI...'})}\n\n"

            config = load_config()
            brief = extract_sales_brief(markdown, config)

            yield f"data: {json.dumps({'type': 'complete', 'brief': brief.model_dump()})}\n\n"

        except Exception as e:
            logger.exception("Error in /api/brief")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
