"""The nine meeting tools and their per-meeting state."""

import asyncio
import logging
import time
from collections.abc import Awaitable
from ipaddress import ip_address
from urllib.parse import urlsplit

from livekit.agents import AgentSession, RunContext, StopResponse, ToolError, function_tool

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
        self.is_ignoring = False
        self.listening_since: float | None = None
        self._ignore_interruption: asyncio.Future[None] | None = None

    @property
    def is_muted(self) -> bool:
        return not self.session.output.audio_enabled

    def _require_active_request(self, context: RunContext) -> None:
        if self.is_ignoring or context.speech_handle.interrupted:
            raise StopResponse()

    async def _call_recall(self, request: Awaitable[None]) -> None:
        try:
            await request
        except RecallError as error:
            raise ToolError(str(error)) from error

    async def _confirm_control(self, message: str) -> None:
        try:
            await self.client.send_chat_message(self.bot_id, message)
        except RecallError:
            # The control is already applied; do not undo it or retry the message.
            logger.warning("Could not confirm the agent control in chat; not retrying")

    @function_tool()
    async def show_webpage(self, url: str, context: RunContext) -> str:
        """Show or replace a public HTTPS page using the supplied URL.

        Displays the page without reading its contents, interacting, or posting
        its link. Announces the loading delay automatically when speech is enabled.
        """
        self._require_active_request(context)
        url = public_webpage_url(url)
        await context.wait_for_playout()
        self._require_active_request(context)
        if not self.is_muted:
            announcement = context.session.say(
                "The screen share may take a couple of seconds to appear.",
                allow_interruptions=True,
            )
            await announcement.wait_for_playout()
        self._require_active_request(context)
        await self._call_recall(self.client.show_webpage(self.bot_id, url))
        self.current_page_url = url
        return "Recall accepted the webpage share request. Page visibility is unverified."

    @function_tool()
    async def send_chat_message(self, message: str, context: RunContext) -> str:
        """Post the requested text to everyone in meeting chat.

        Use send_current_page_link for the most recently selected page's link.
        """
        self._require_active_request(context)
        if not message.strip() or len(message) > 500:
            raise ToolError("Google Meet messages must contain 1 to 500 characters.")
        await self._call_recall(self.client.send_chat_message(self.bot_id, message))
        return "Recall accepted the chat message."

    @function_tool()
    async def send_current_page_link(self, context: RunContext) -> str:
        """Post the exact most recently selected page URL to meeting chat.

        Works after sharing stops. Ask for a webpage first if none has been selected.
        """
        self._require_active_request(context)
        if self.current_page_url is None:
            raise ToolError("No page has been selected. Ask for a webpage URL first.")
        return await self.send_chat_message(self.current_page_url, context)

    @function_tool()
    async def stop_sharing(self, context: RunContext) -> str:
        """Stop the webpage screen share while keeping the agent available."""
        self._require_active_request(context)
        await self._call_recall(self.client.stop_sharing(self.bot_id))
        return "Recall accepted the request to stop sharing."

    @function_tool()
    async def leave_call(self, context: RunContext) -> str:
        """Remove only this bot from the meeting.

        Say 'Goodbye' before calling when speech is enabled. Use stop_sharing to
        end a screen share without leaving.
        """
        self._require_active_request(context)
        await context.wait_for_playout()
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
        await self._confirm_control("Muted. Tools still work.")
        return "Speech muted."

    @function_tool()
    async def unmute_agent(self, context: RunContext) -> str:
        """Enable speech without changing listening state."""
        self._require_active_request(context)
        self.session.output.set_audio_enabled(True)
        self.session.output.set_transcription_enabled(True)
        await self._confirm_control("Unmuted.")
        return "Speech enabled."

    @function_tool()
    async def ignore_agent(self, context: RunContext) -> None:
        """Stop answering and acting until 'listen', preserving the mute setting."""
        self._require_active_request(context)
        self.is_ignoring = True
        # Awaiting here would wait for this tool's own speech handle to finish.
        self._ignore_interruption = self.session.interrupt(force=True)
        speech = "muted" if self.is_muted else "enabled"
        await self._confirm_control(f"Ignoring requests. Speech remains {speech}.")
        raise StopResponse()

    @function_tool()
    async def listen_agent(self, context: RunContext) -> str:
        """Resume accepting new requests without changing the speech mute setting."""
        if context.speech_handle.interrupted:
            raise StopResponse()
        if self.is_ignoring:
            if self._ignore_interruption is not None:
                await asyncio.shield(self._ignore_interruption)
            if context.speech_handle.interrupted:
                raise StopResponse()
            self.session.clear_user_turn()
            self.listening_since = time.time()
            self.is_ignoring = False
        speech = "muted" if self.is_muted else "enabled"
        await self._confirm_control(f"Listening. Speech is {speech}.")
        return "Listening. Speech mute setting unchanged."

    def tools(self) -> list:
        return [
            self.show_webpage,
            self.send_chat_message,
            self.send_current_page_link,
            self.stop_sharing,
            self.leave_call,
            self.mute_agent,
            self.unmute_agent,
            self.ignore_agent,
            self.listen_agent,
        ]
