# agent-demo-livekit

A small agent demo featuring [Recall.ai's Output Media API](https://docs.recall.ai/docs/stream-media) and [LiveKit](https://livekit.io/). It includes an interactive avatar you can command through nine tool calls.

## Behavior

Address the avatar as **“Assistant”**, followed by a command such as “start a screen share of https://example.com.” Each tool call posts its result in meeting chat; requested messages and links are their own confirmation.

| Action | Tool |
| --- | --- |
| Start or replace a screen share with a public webpage; post a loading notice | `start_screenshare(url)` |
| Post text in meeting chat | `send_chat_message(message)` |
| Post the most recently shared page's exact link | `send_current_page_link()` |
| Stop the screen share | `stop_screenshare()` |
| Post a departure message and leave the meeting | `leave_call()` |
| Silence speech; keep tools available | `mute_agent()` |
| Enable speech | `unmute_agent()` |
| Stop answering and acting | `ignore_agent()` |
| Resume requests; preserve the mute setting | `listen_agent()` |

## Requirements

> **[Talk to us](https://recall.ai/book-agent-demo) before you start.** This demo requires us to enable feature flags on your Recall workspace.

- Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
- A Recall workspace with the LiveKit integration enabled and a REST API key.
- A LiveKit Cloud project with credentials and access to Inference for STT, LLM, and TTS.
- A Runway API key with Characters access and a character preset.
- A Google account to host the meeting.

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
| `RECALL_API_BASE_URL` | Matching regional API URL, such as `https://us-west-2.recall.ai/api/v1`. |
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

Create and join a meeting at [meet.new](https://meet.new). Paste its URL into the launcher and select **Send agent**, then admit **livekit demo** if prompted. The form confirms the request was accepted; joining and avatar startup take additional time. The bot joins silently and posts a short introduction in meeting chat.

This launcher currently accepts Google Meet URLs and creates `web_4_core` Google Meet bots. Using another meeting platform requires updating the launcher validation and bot configuration.

### 7. Try a request and finish the demo

Say “Assistant, start a screen share of https://example.com.” Expect one chat confirmation that includes the loading notice. Use the manual demonstration below to try all nine tools.

When finished, say “Assistant, leave,” then stop both terminal processes with Ctrl+C. If the agent is ignoring requests, say “Assistant, listen” first.

The avatar's default session limit is 10 minutes; launch another bot to repeat the demo. Restart the worker after changing code or voice settings; restart both processes after changing shared connection settings.

## Manual demonstration

Start with a fresh bot: it should join silently and post one introduction. Follow these steps in order, saying each quoted command separately.

1. **Check conversation.**

   **Say:** “Assistant, what is two plus two?”

   **Expect:** One short spoken answer.

2. **Start a screen share and get its link.**

   **Say:** “Assistant, start a screen share of https://example.com.” After the page appears, say “Assistant, send that link in chat.”

   **Expect:** A loading notice in chat, the shared page, then its exact URL in chat.

3. **Post a message and stop sharing.**

   **Say:** “Assistant, post Hello from the demo in chat.” Then: “Assistant, stop the screen share.”

   **Expect:** The requested text, then a stop confirmation in chat. The screen share ends.

4. **Mute speech while keeping tools available.**

   **Say:** “Assistant, mute.” Then: “Assistant, post Muted test in chat.”

   **Expect:** A mute confirmation and the requested text in chat, with no speech.

5. **Restore speech.**

   **Say:** “Assistant, unmute.” Then: “Assistant, what is two plus two?”

   **Expect:** An unmute confirmation in chat and a short spoken answer. No muted answers or actions replay.

6. **Ignore requests.**

   **Say:** “Assistant, ignore.” Then: “Assistant, post Ignore test in chat.”

   **Expect:** An ignore confirmation, followed by no message or action. Requests to unmute or leave should also be ignored.

7. **Resume listening.**

   **Say:** “Assistant, listen” as a standalone command. Then: “Assistant, post Listening test in chat.”

   **Expect:** A listen confirmation and the new message in chat. Ignored requests do not replay.

8. **Check that listening does not unmute speech.**

   **Say:** “Assistant, mute,” then “Assistant, ignore,” then “Assistant, listen.” Request another screen share, its link, and then stop sharing.

   **Expect:** A chat confirmation after each tool, with speech still muted throughout.

9. **Leave the meeting.**

   **Say:** “Assistant, leave” while still muted.

   **Expect:** “Leaving the call.” in chat, followed by the bot leaving. Your meeting stays open.

Additional checks:

- Repeat mute, unmute, or listen: the requested state should stay the same and each accepted command should confirm in chat.
- Discuss or quote commands without directing them at the avatar: its state should not change. While ignoring, only a standalone addressed “listen” request should resume it.
- During a longer answer, ordinary conversation should not interrupt it. A request addressed to “Assistant” can interrupt once its transcript is complete.

Perform the demonstration manually and record results outside the repository. The sample contains no evaluator or test harness.

## Code map

| File | Responsibility |
| --- | --- |
| `app/web.py` | Serve the form and create a Recall bot. |
| `app/templates/index.html` | Single form and request status. |
| `app/agent.py` | Instructions, voice-session configuration, avatar startup, and cleanup. |
| `app/meeting_agent.py` | Filter speech before interruption and gate ignored turns except listen. |
| `app/meeting_tools.py` | Nine tools, listening/mute state, and the current page URL. |
| `app/speech_output.py` | Drop muted avatar audio without cancelling tools. |
| `app/recall_client.py` | Recall HTTP requests and clear errors. |
| `app/config.py` | Load `.env` and define the fixed bot name. |

Recall connects the meeting to LiveKit and supplies its bot ID and regional API URL. Runway turns synthesized speech into synchronized audio and animated video, which Recall outputs through the bot's camera. Five tools call Recall; four control speech and request processing locally.

Speech is filtered before it can interrupt an answer or enter the conversation. Requests are accepted once STT provides their complete transcript.

Muting disables future speech synthesis and drops avatar audio already in flight, while leaving tools available. Ignored requests are discarded except for a standalone addressed listen command; they cannot replay after listening resumes.

## Boundaries and troubleshooting

- The agent cannot see meeting video or read, click, scroll, sign in to, or summarize shared webpages. Sharing displays a public HTTPS page; it does not give the agent browser control.
- Showing a page does not automatically post its link. The last accepted URL remains available after sharing stops or a later share fails.
- An accepted request does not prove the page visibly loaded. Some websites block automated browsers. Check the meeting before retrying an uncertain action.
- Meeting chat messages are limited to 500 characters.
- There is no database, search feature, transcript storage, webhook receiver, or cloud deployment requirement.
- The launcher has no application authentication; keep it bound to localhost.

If the bot stays silent, check the name prefix, ignore state, and mute state first, then inspect the worker terminal. Connection failures usually mean mismatched regional Recall settings, LiveKit credentials or dispatch names, or unavailable inference/avatar access. Fill any missing `.env` setting named by an error and restart the affected process.

If ignoring, say “Assistant, listen” first. Ask “Assistant, leave” before stopping the worker and web server with Ctrl+C. If a provider fails, check Meet and Recall and remove any remaining demo bot.

Reference: [Recall Output Media](https://docs.recall.ai/docs/stream-media).
