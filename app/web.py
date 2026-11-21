"""Serve the one-field launcher and create a bot for its meeting URL."""

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
    def validate_url(cls, value: str) -> str:
        url = value.strip()
        error = "Enter a direct HTTPS meeting link from Zoom, Google Meet, Microsoft Teams, or Webex."
        try:
            parsed = urlsplit(url)
        except ValueError:
            raise ValueError(error) from None

        if (
            parsed.scheme != "https"
            or parsed.username is not None
            or "\\" in url
            or any(char.isspace() or ord(char) < 32 for char in url)
        ):
            raise ValueError(error)

        host = parsed.hostname or ""
        if host == "meet.google.com":
            # Preserve the existing room key for duplicate submissions.
            if (
                parsed.netloc == host
                and not parsed.fragment
                and re.fullmatch(r"/[a-z]{3}-[a-z]{4}-[a-z]{3}/?", parsed.path)
            ):
                return f"https://meet.google.com{parsed.path.rstrip('/')}"
            return url
        if host in {"teams.microsoft.com", "teams.cloud.microsoft", "teams.live.com"} or any(
            host == domain or host.endswith("." + domain)
            for domain in ("zoom.us", "zoom.com", "zoom-x.de", "webex.com")
        ):
            return url
        raise ValueError(error)


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
