"""Discard muted audio before it reaches the avatar, without cancelling tools."""

from livekit import rtc
from livekit.agents.voice import io


class SpeechOutput(io.AudioOutput):
    def __init__(self, output: io.AudioOutput):
        super().__init__(
            label="speech-mute",
            next_in_chain=output,
            sample_rate=output.sample_rate,
            capabilities=io.AudioOutputCapabilities(pause=output.can_pause),
        )
        self._output = self.next_in_chain
        assert self._output is not None
        self._muted = False
        self._capturing = False
        self._discard_segment = False

    async def capture_frame(self, frame: rtc.AudioFrame) -> None:
        self._capturing = True
        self._discard_segment |= self._muted
        if self._discard_segment:
            return
        await super().capture_frame(frame)
        await self._output.capture_frame(frame)
        if self._muted:
            self.clear_buffer()  # A pending capture may have completed after mute.

    def flush(self) -> None:
        super().flush()
        self._output.flush()
        self._capturing = self._discard_segment = False

    def clear_buffer(self) -> None:
        self._output.clear_buffer()

    def on_detached(self) -> None:
        self._muted = True
        self._discard_segment |= self._capturing
        self.clear_buffer()
        super().on_detached()

    def on_attached(self) -> None:
        self._muted = False
        super().on_attached()
