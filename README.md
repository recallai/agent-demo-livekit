# agent-demo-livekit

Send an interactive meeting agent to Google Meet, Zoom, Microsoft Teams, or Webex. It appears as a speaking avatar, answers questions aloud, and takes spoken requests to share a webpage, post in chat, or leave the call.

LiveKit runs the voice session, Runway animates the avatar, and Recall connects the agent to the meeting. [LiveKit](https://livekit.io/) · [Recall's Meeting Agent API](https://docs.recall.ai/docs/stream-media) · [Recall.ai LiveKit Demo](https://youtu.be/as4ggeUyjLI) · [Recall.ai LiveKit Tutorial](https://www.recall.ai/blog/how-to-build-a-livekit-agent-for-meetings-with-recall-ai)

[![Demo video](livekitDemoImage.png)](https://youtu.be/as4ggeUyjLI)

## Behavior

Address the avatar as **“Assistant”**, followed by a command such as “start a screen share of https://example.com.” Where meeting chat is available, each tool call posts its result there. Requested messages and links are their own confirmation.

| Action | Tool |
| --- | --- |
| Start or replace a screen share with a public webpage; post a loading notice | `start_screenshare(url)` |
| Post text in meeting chat | `send_chat_message(message)` |
| Post the most recently shared page's exact link | `send_current_page_link()` |
| Stop the screen share | `stop_screenshare()` |
| Post a departure message and leave the meeting | `leave_call()` |
| Silence speech; keep tools available | `mute_agent()` |
| Enable speech | `unmute_agent()` |
| Stop listening for requests | `stop_listening()` |
| Start listening for requests; preserve the mute setting | `start_listening()` |

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
- A Recall workspace and a REST API key.
- A LiveKit Cloud project with credentials and access to Inference for STT, LLM, and TTS.
- A Runway API key with Characters access and a character preset.
- A meeting account on one of the supported platforms.

## Quickstart

Set up and run the sample locally.

### 1. Clone the repository and install dependencies

```sh
git clone https://github.com/recallai/agent-demo-livekit.git
cd agent-demo-livekit
uv sync --locked
```

### 2. Configure the environment

Create the local configuration file:

```sh
cp .env.example .env
```

Fill in the root `.env`. It is ignored by Git and never sent to the browser. Both processes load it; existing process environment variables take precedence.

| Variable | Value |
| --- | --- |
| `RECALL_API_KEY` | REST API key for your Recall workspace. |
| `RECALL_API_BASE_URL` | Regional API URL for the launcher, such as `https://us-west-2.recall.ai/api/v1`. |
| `LIVEKIT_URL` | Your project's websocket URL. |
| `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | Matching LiveKit project credentials. |
| `LIVEKIT_AGENT_NAME` | Worker dispatch name; use the same value for both processes. |
| `RUNWAYML_API_SECRET` | Separate Runway API key with Characters access. |
| `RUNWAY_PRESET_ID` | Avatar preset; the example uses Mina (`music-superstar`). |
| `RUNWAY_MAX_DURATION` | Avatar session limit; `600` seconds in the example. |
| `STT_MODEL`, `LLM_MODEL` | LiveKit Inference model IDs from the example. |
| `TTS_MODEL`, `TTS_VOICE` | The example uses `rime/coda` and `astra`. |

For Runway setup, see [LiveKit's Runway guide](https://docs.livekit.io/agents/models/avatar/plugins/runway/). The app passes the preset ID to Runway while LiveKit supplies the agent's voice and instructions.

### 3. Connect Recall to LiveKit

Open [Agents → LiveKit in the Recall dashboard](https://us-west-2.recall.ai/dashboard/agents/livekit). Select the region and workspace matching `RECALL_API_KEY`, then enter the `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` values from `.env`.

### 4. Start the agent worker

From the repository root:

```sh
uv run --locked python -m app.agent dev
```

Wait for the terminal to report that the worker has registered. Keep this process running.

### 5. Start the launcher

Open another terminal in the repository root:

```sh
uv run --locked uvicorn app.web:app --host 127.0.0.1 --port 8000
```

Keep this process running alongside the worker, then open [the launcher](http://127.0.0.1:8000).

### 6. Send the agent to a meeting

For your first test, start a Google Meet call at [meet.new](https://meet.new/). Paste the direct meeting link into the launcher, select **Send agent**, and admit **livekit demo** if prompted. The launcher requests a four-core bot.

### 7. Try the agent

Try the chat commands in a meeting that allows bot chat. [Recall chat support](https://docs.recall.ai/docs/sending-chat-messages)

| Try saying |
| --- |
| “Assistant, what is two plus two?” |
| “Assistant, share the LiveKit homepage.” |
| “Assistant, give me the page URL.” |
| “Assistant, mute.” |
| “Assistant, post Hello from the demo in chat.” |
| “Assistant, stop the screen share.” |
| “Assistant, unmute.” |
| “Assistant, stop listening.” |
| “Assistant, start listening.” |
| “Assistant, leave the meeting.” |

After the bot leaves, stop both terminal processes with Ctrl+C.

The avatar has a default session limit; launch another bot to repeat the demo.

## Code map

| File | Responsibility |
| --- | --- |
| `app/web.py` | Serve the form and create a Recall bot. |
| `app/templates/index.html` | Single form and request status. |
| `app/agent.py` | Instructions, voice-session configuration, avatar startup, and cleanup. |
| `app/meeting_agent.py` | Filter speech before interruption; admit only start listening while paused. |
| `app/meeting_tools.py` | Nine tools, listening/mute state, and the current page URL. |
| `app/speech_output.py` | Drop muted avatar audio without cancelling tools. |
| `app/recall_client.py` | Recall HTTP requests and clear errors. |
| `app/config.py` | Load `.env` and define the fixed bot name. |

The worker reads `recall.bot_id` and `recall.api_base_url` from LiveKit's [job dispatch metadata](https://docs.recall.ai/docs/meeting-agents-livekit#use-recall-bot-context-in-tools). The metadata URL is the regional origin, such as `https://us-west-2.recall.ai`; the worker adds `/api/v1` for Recall requests. Your Recall API key stays in `.env`.

Runway turns synthesized speech into synchronized audio and animated video, which Recall outputs through the bot's camera. Five tools call Recall; four control speech and request processing locally.

Speech is filtered before it can interrupt an answer or enter the conversation. Requests are accepted once STT provides their complete transcript.

Muting disables future speech synthesis and drops avatar audio already in flight, while leaving tools available. Stopping listening discards requests except for a standalone addressed “start listening” command; skipped requests cannot replay when listening resumes.

## Boundaries and troubleshooting

- Where chat is available, check it for recent commands and the agent's mute or listening status.
- Chat messages are limited to 500 characters.
- If the bot doesn't respond, make sure to clearly say “Assistant” before your command.
