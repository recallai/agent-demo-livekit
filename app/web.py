"""Serve the one-field launcher and create a bot for its meeting URL."""

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from app.config import ROOT, require_env
from app.recall_client import RecallClient, RecallError

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
pending_meetings: set[str] = set()


class MeetingRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    meeting_url: str


@app.get("/")
async def index():
    return FileResponse(ROOT / "app" / "templates" / "index.html")


@app.post("/api/bots", status_code=201)
async def create_meeting_agent(request: MeetingRequest):
    if request.meeting_url in pending_meetings:
        raise HTTPException(409, "An agent request for this meeting is already in progress.")
    pending_meetings.add(request.meeting_url)
    try:
        async with RecallClient(
            require_env("RECALL_API_KEY"), require_env("RECALL_API_BASE_URL")
        ) as client:
            bot_id = await client.create_bot(
                request.meeting_url,
                require_env("LIVEKIT_AGENT_NAME"),
            )
        return {
            "bot_id": bot_id,
            "message": "Agent requested. Admit livekit demo if prompted.",
        }
    except ValueError as error:
        raise HTTPException(503, str(error)) from error
    except RecallError as error:
        raise HTTPException(502, str(error)) from error
    finally:
        pending_meetings.discard(request.meeting_url)
