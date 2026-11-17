"""LiveKit entrypoint: connect to one meeting, converse, and close its resources."""

import asyncio
import json
import logging
from uuid import UUID

from livekit import agents
from livekit.agents import (
    AgentServer,
    AgentSession,
    TurnHandlingOptions,
    inference,
    room_io,
)
from livekit.plugins import runway

from app.config import BOT_NAME, require_env
from app.meeting_agent import MeetingAgent
from app.meeting_tools import MeetingTools
from app.recall_client import RecallClient, RecallError
from app.speech_output import SpeechOutput

logger = logging.getLogger("meeting-demo")
server = AgentServer(num_idle_processes=1)

INSTRUCTIONS = """You are livekit demo, a concise meeting assistant that hears audio only.
Act only on direct requests starting with 'Assistant' or 'livekit demo'. Name
mentions, quotes, discussion, and hypothetical commands are not requests.
Join silently. A chat introduction is posted automatically; never repeat it aloud.
Answer in one short sentence unless asked for detail. Do not greet, offer help,
suggest next steps, or ask unsolicited questions. Clarify only when needed.

Use tools only for requested actions. Follow the tool's instructions without
filler or spoken recaps. Starting a screen share does not authorize posting its link;
when both are requested, share successfully before sending the exact stored link.
Report only what tools confirm. Never claim an accepted share visibly loaded,
read unseen page contents, or retry an uncertain action automatically.

Speech and listening are independent. Mute/unmute controls speech only; meeting
tools keep working while muted. 'Stop listening' stops answers and actions until a
separate addressed 'start listening' command. Both preserve mute. Every tool provides
its own meeting-chat feedback; do not add duplicate chat messages or spoken recaps.
Never replay unheard answers or ignored requests, or repeat actions.
"""

INTRO_CHAT_MESSAGE = (
    "Start requests with 'Assistant, [command]'.\n\n"
    "See the full list of commands here:\n"
    "https://github.com/recallai/agent-demo-livekit#7-try-the-agent"
)


def meeting_bot_id(metadata: str, expected_api_url: str) -> str:
    try:
        recall = json.loads(metadata)["recall"]
        bot_id = str(UUID(recall["bot_id"]))
        api_url = recall["api_base_url"].rstrip("/")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise ValueError("The job must contain Recall bot ID and API URL metadata.") from error
    if api_url != expected_api_url.rstrip("/"):
        raise ValueError("The meeting's Recall region does not match .env.")
    return bot_id


def create_voice_session() -> AgentSession:
    return AgentSession(
        vad=None,
        stt=inference.STT(model=require_env("STT_MODEL"), language="en"),
        llm=inference.LLM(
            model=require_env("LLM_MODEL"),
            extra_kwargs={"parallel_tool_calls": False},
        ),
        tts=inference.TTS(
            model=require_env("TTS_MODEL"),
            voice=require_env("TTS_VOICE"),
        ),
        turn_handling=TurnHandlingOptions(
            turn_detection="stt",
            preemptive_generation={"enabled": False},
            interruption={"resume_false_interruption": False},
        ),
    )


@server.rtc_session(agent_name=require_env("LIVEKIT_AGENT_NAME"))
async def entrypoint(ctx: agents.JobContext) -> None:
    api_url = require_env("RECALL_API_BASE_URL")
    bot_id = meeting_bot_id(ctx.job.metadata, api_url)
    finished = asyncio.Event()
    session: AgentSession | None = None
    avatar: runway.AvatarSession | None = None
    meeting_identity: str | None = None
    session_error: Exception | None = None

    @ctx.room.on("disconnected")
    def on_room_disconnected(_) -> None:
        finished.set()

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant) -> None:
        nonlocal session_error
        if participant.identity == meeting_identity:
            finished.set()
        elif (
            avatar is not None
            and participant.identity == avatar.avatar_identity
            and not finished.is_set()
        ):
            session_error = RuntimeError("The speaking avatar disconnected.")
            finished.set()

    async with RecallClient(require_env("RECALL_API_KEY"), api_url) as client:
        try:
            session = create_voice_session()

            @session.on("close")
            def on_session_closed(event) -> None:
                nonlocal session_error
                if event.error is not None:
                    session_error = event.error.error
                elif event.reason == "error":
                    session_error = RuntimeError("The agent session closed after an error.")
                finished.set()

            await ctx.connect(auto_subscribe=agents.AutoSubscribe.AUDIO_ONLY)
            meeting = await asyncio.wait_for(ctx.wait_for_participant(), timeout=30)
            meeting_identity = meeting.identity
            avatar = runway.AvatarSession(
                preset_id=require_env("RUNWAY_PRESET_ID"),
                api_key=require_env("RUNWAYML_API_SECRET"),
                avatar_participant_name=BOT_NAME,
                max_duration=int(require_env("RUNWAY_MAX_DURATION")),
            )
            # AvatarSession registers its own job-shutdown cleanup.
            await avatar.start(session, room=ctx.room)
            await avatar.wait_for_join()
            try:
                await client.send_chat_message(bot_id, INTRO_CHAT_MESSAGE)
            except RecallError:
                logger.warning("Could not confirm the introductory chat message; not retrying")
            tools = MeetingTools(client, bot_id, session)
            await session.start(
                room=ctx.room,
                agent=MeetingAgent(instructions=INSTRUCTIONS, meeting_tools=tools),
                room_options=room_io.RoomOptions(
                    participant_identity=meeting.identity,
                    audio_output=False,
                    video_input=False,
                    close_on_disconnect=True,
                ),
            )
            # Gate in-flight avatar audio as well as future speech, without cancelling tools.
            avatar_audio = session.output.audio
            if avatar_audio is None:
                raise RuntimeError("The avatar did not provide an audio output.")
            session.output.audio = SpeechOutput(avatar_audio)
            await finished.wait()
            if session_error is not None:
                raise session_error
        except Exception:
            try:
                await client.leave_call(bot_id)
            except RecallError:
                logger.warning("Could not confirm bot departure after an agent error")
            raise
        finally:
            try:
                if session is not None:
                    await session.aclose()
            except Exception:
                logger.exception("Could not close the agent session cleanly")
            finally:
                ctx.shutdown(reason="Meeting demo finished")
                logger.info("Meeting agent session closed")


if __name__ == "__main__":
    agents.cli.run_app(server)
