"""The nine meeting tools and their per-meeting state."""

import asyncio
import logging
import time
from collections.abc import Awaitable
from ipaddress import ip_address
from urllib.parse import urlsplit

from livekit.agents import (
    AgentSession,
    RunContext,
    StopResponse,
    ToolError,
    function_tool,
)

from app.recall_client import RecallClient, RecallError

logger = logging.getLogger("meeting-demo")


def public_webpage_url(value: str) -> str:
    url = value.strip()
    try:
        parsed = urlsplit(url)
        hostname = (parsed.hostname or "").rstrip(".").lower()
        valid = (
            parsed.scheme == "https"
            and hostname
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
            and not any(character.isspace() for character in url)
        )
    except ValueError:
        valid = False
        hostname = ""
    if not valid:
        raise ToolError("Provide a public HTTPS webpage URL without login credentials.")
    try:
        is_public = ip_address(hostname).is_global
    except ValueError:
        is_public = "." in hostname and not hostname.endswith(
            (".localhost", ".local", ".internal")
        )
    if not is_public:
        raise ToolError("Use a public website, not a local or private network address.")
    return url


class MeetingTools:
    def __init__(self, client: RecallClient, bot_id: str, session: AgentSession):
        self.client = client
        self.bot_id = bot_id
        self.session = session
        self.current_page_url: str | None = None
        self.is_listening = True
        self.listening_since: float | None = None
        self._stop_listening_interruption: asyncio.Future[None] | None = None

    @property
    def is_muted(self) -> bool:
        return not self.session.output.audio_enabled

    def _require_active_request(self, context: RunContext) -> None:
        if not self.is_listening or context.speech_handle.interrupted:
            raise StopResponse()

    async def _call_recall(self, request: Awaitable[None]) -> None:
        try:
            await request
        except RecallError as error:
            await self._post_status(str(error))
            raise ToolError(str(error)) from error

    async def _post_status(self, message: str) -> None:
        try:
            await self.client.send_chat_message(self.bot_id, message)
        except RecallError:
            # Feedback must not undo an action or trigger an automatic retry.
            logger.warning("Could not post tool status in chat; not retrying")

    @function_tool()
    async def start_screenshare(self, url: str, context: RunContext) -> str:
        """Start or replace a screen share displaying a public HTTPS webpage.

        Displays the page without reading its contents, interacting, or posting
        its link. Posts a loading notice in chat and speaks it when speech is enabled.
        """
        self._require_active_request(context)
        try:
            url = public_webpage_url(url)
        except ToolError as error:
            await self._post_status(str(error))
            raise
        await context.wait_for_playout()
        self._require_active_request(context)
        if not self.is_muted:
            announcement = context.session.say(
                "The screen share may take a couple of seconds to appear.",
                allow_interruptions=True,
            )
            await announcement.wait_for_playout()
        self._require_active_request(context)
        await self._call_recall(self.client.start_screenshare(self.bot_id, url))
        self.current_page_url = url
        await self._post_status("Screen share requested. It may take a few seconds to appear.")
        return "Recall accepted the screen share request. Page visibility is unverified."

    @function_tool()
    async def send_chat_message(self, message: str, context: RunContext) -> str:
        """Post the requested text to everyone in meeting chat.

        Use send_current_page_link for the most recently selected page's link.
        """
        self._require_active_request(context)
        if not message.strip() or len(message) > 500:
            await self._post_status("Message not sent: use 1 to 500 characters.")
            raise ToolError("Chat messages must contain 1 to 500 characters.")
        await self._call_recall(self.client.send_chat_message(self.bot_id, message))
        return "Recall accepted the chat message."

    @function_tool()
    async def send_current_page_link(self, context: RunContext) -> str:
        """Post the exact most recently selected page URL to meeting chat.

        Works after sharing stops. Ask for a webpage first if none has been selected.
        """
        self._require_active_request(context)
        if self.current_page_url is None:
            await self._post_status("No webpage has been selected yet. Ask me to show one first.")
            raise ToolError("No page has been selected. Ask for a webpage URL first.")
        return await self.send_chat_message(self.current_page_url, context)

    @function_tool()
    async def stop_screenshare(self, context: RunContext) -> str:
        """Stop the webpage screen share while keeping the agent available."""
        self._require_active_request(context)
        await self._call_recall(self.client.stop_screenshare(self.bot_id))
        await self._post_status("Stopped sharing.")
        return "Recall accepted the request to stop sharing."

    @function_tool()
    async def leave_call(self, context: RunContext) -> str:
        """Remove only this bot from the meeting.

        Say 'Goodbye' before calling when speech is enabled. Use stop_screenshare to
        end a screen share without leaving.
        """
        self._require_active_request(context)
        await context.wait_for_playout()
        self._require_active_request(context)
        await self._post_status("Leaving the call.")
        self._require_active_request(context)
        await self._call_recall(self.client.leave_call(self.bot_id))
        # Schedule shutdown instead of waiting for this tool's own session to close.
        context.session.shutdown(drain=False)
        return "Recall accepted the request for this bot to leave."

    @function_tool()
    async def mute_agent(self, context: RunContext) -> str:
        """Silence speech without changing listening state or blocking meeting tools."""
        self._require_active_request(context)
        self.session.output.set_audio_enabled(False)
        self.session.output.set_transcription_enabled(False)
        await self._post_status("Muted. Tools still work.")
        return "Speech muted."

    @function_tool()
    async def unmute_agent(self, context: RunContext) -> str:
        """Enable speech without changing listening state."""
        self._require_active_request(context)
        self.session.output.set_audio_enabled(True)
        self.session.output.set_transcription_enabled(True)
        await self._post_status("Unmuted.")
        return "Speech enabled."

    @function_tool()
    async def stop_listening(self, context: RunContext) -> None:
        """Stop answers and actions until 'start listening', preserving mute."""
        self._require_active_request(context)
        self.is_listening = False
        # Awaiting here would wait for this tool's own speech handle to finish.
        self._stop_listening_interruption = self.session.interrupt(force=True)
        speech = "muted" if self.is_muted else "enabled"
        await self._post_status(f"Stopped listening. Speech remains {speech}.")
        raise StopResponse()

    @function_tool()
    async def start_listening(self, context: RunContext) -> str:
        """Resume accepting new requests without changing the speech mute setting."""
        if context.speech_handle.interrupted:
            raise StopResponse()
        if not self.is_listening:
            if self._stop_listening_interruption is not None:
                await asyncio.shield(self._stop_listening_interruption)
            if context.speech_handle.interrupted:
                raise StopResponse()
            self.session.clear_user_turn()
            self.listening_since = time.time()
            self.is_listening = True
        speech = "muted" if self.is_muted else "enabled"
        await self._post_status(f"Started listening. Speech is {speech}.")
        return "Listening. Speech mute setting unchanged."

    def tools(self) -> list:
        return [
            self.start_screenshare,
            self.send_chat_message,
            self.send_current_page_link,
            self.stop_screenshare,
            self.leave_call,
            self.mute_agent,
            self.unmute_agent,
            self.stop_listening,
            self.start_listening,
        ]
