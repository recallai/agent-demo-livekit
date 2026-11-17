"""Serve the one-field launcher and create a bot for its Google Meet URL."""

import re
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from app.config import ROOT, require_env
from app.recall_client import RecallClient, RecallError

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
pending_meetings: set[str] = set()


class MeetingRequest(BaseModel):
    meeting_url: str

    @field_validator("meeting_url")
    @classmethod
    def validate_meeting_url(cls, value: str) -> str:
        parsed = urlsplit(value.strip())
        if (
            parsed.scheme != "https"
            or parsed.netloc != "meet.google.com"
            or not re.fullmatch(r"/[a-z]{3}-[a-z]{4}-[a-z]{3}/?", parsed.path)
        ):
            raise ValueError("Enter a Google Meet URL, such as https://meet.google.com/abc-defg-hij.")
        return f"https://meet.google.com{parsed.path.rstrip('/')}"


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
            "message": "Agent requested. Admit it in Google Meet if prompted.",
        }
    except ValueError as error:
        raise HTTPException(503, str(error)) from error
    except RecallError as error:
        raise HTTPException(502, str(error)) from error
    finally:
        pending_meetings.discard(request.meeting_url)
