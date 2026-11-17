"""Only pass requests addressed to the demo assistant into its conversation."""

import re
from collections.abc import AsyncIterable
from dataclasses import replace

from livekit import rtc
from livekit.agents import (
    Agent,
    FlushSentinel,
    ModelSettings,
    StopResponse,
    UserTurnExceededEvent,
    llm,
    stt,
)

from app.meeting_tools import MeetingTools

ADDRESSED_REQUEST = re.compile(
    r"^\s*(?:(?:hey|hi|hello|ok|okay)[,\s]+)?(?:assistant|live\s*kit\s+demo)\b",
    re.IGNORECASE,
)
START_LISTENING_COMMAND = re.compile(
    r"[\s,.:;-]*(?:please\s+)?start\s+listening(?:\s+please)?[.!]?\s*", re.IGNORECASE
)


class MeetingAgent(Agent):
    def __init__(self, *, instructions: str, meeting_tools: MeetingTools):
        super().__init__(instructions=instructions, tools=meeting_tools.tools())
        self.meeting_tools = meeting_tools

    def _accepts_request(self, text: str, started_at: float | None) -> bool:
        addressed = ADDRESSED_REQUEST.match(text)
        if not addressed:
            return False
        listening_since = self.meeting_tools.listening_since
        if listening_since is not None and (started_at is None or started_at <= listening_since):
            # Delayed transcription must not replay speech from before listening resumed.
            return False
        return self.meeting_tools.is_listening or bool(
            START_LISTENING_COMMAND.fullmatch(text[addressed.end():])
        )

    async def stt_node(
        self, audio: AsyncIterable[rtc.AudioFrame], model_settings: ModelSettings
    ) -> AsyncIterable[stt.SpeechEvent]:
        # Filter complete STT segments before LiveKit can interrupt the current reply.
        # Raw VAD is disabled; accepted transcripts still use STT's turn boundaries.
        start: stt.SpeechEvent | None = None
        accepted = False
        async for event in Agent.default.stt_node(self, audio, model_settings):
            if event.type == stt.SpeechEventType.START_OF_SPEECH:
                start = replace(event, speech_start_time=event.speech_start_time or event.created_at)
                accepted = False
            elif event.type == stt.SpeechEventType.FINAL_TRANSCRIPT:
                text = event.alternatives[0].text if event.alternatives else ""
                started_at = start.speech_start_time if start else event.created_at
                if (
                    not self.meeting_tools.is_listening or not accepted
                ) and not self._accepts_request(text, started_at):
                    continue
                if start is not None:
                    yield start
                    start = None
                accepted = True
                yield event
            elif event.type == stt.SpeechEventType.END_OF_SPEECH:
                if accepted:
                    yield event
                start, accepted = None, False
            elif event.type == stt.SpeechEventType.RECOGNITION_USAGE:
                yield event

    async def on_user_turn_completed(
        self, turn_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ) -> None:
        if not self._accepts_request(
            new_message.text_content or "", new_message.metrics.get("started_speaking_at")
        ):
            raise StopResponse()

    def llm_node(
        self,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        model_settings: ModelSettings,
    ) -> AsyncIterable[llm.ChatChunk | str | FlushSentinel] | None:
        if not self.meeting_tools.is_listening:
            # Only 'start listening' is admitted; keep every other tool unavailable.
            tools = [self.meeting_tools.start_listening]
            model_settings = ModelSettings(
                tool_choice={"type": "function", "function": {"name": "start_listening"}}
            )
        return Agent.default.llm_node(self, chat_ctx, tools, model_settings)

    async def on_user_turn_exceeded(self, event: UserTurnExceededEvent) -> None:
        # Do not bypass the name check with an automatic response to a long turn.
        pass
