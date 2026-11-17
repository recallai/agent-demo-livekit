# agent-demo-livekit

A small agent demo featuring [Recall.ai's Output Media API](https://docs.recall.ai/docs/stream-media) and [LiveKit](https://livekit.io/). It includes an interactive avatar you can command through nine tool calls.

## Behavior

Start every request with **“Assistant”** or **“livekit demo”**; each tool call posts feedback in meeting chat.

| Action | Tool |
| --- | --- |
| Show or replace a public webpage; post a loading notice | `show_webpage(url)` |
| Post text in meeting chat | `send_chat_message(message)` |
| Post the most recently shared page's exact link | `send_current_page_link()` |
| Stop sharing | `stop_sharing()` |
| Post a departure message and leave the meeting | `leave_call()` |
| Silence speech; keep tools available | `mute_agent()` |
| Enable speech | `unmute_agent()` |
| Stop answering and acting | `ignore_agent()` |
| Resume requests; preserve the mute setting | `listen_agent()` |

| Request mode | Speech setting | Speaks when asked | Executes requests |
| --- | --- | --- | --- |
| Listening | Unmuted | Yes | Yes |
| Listening | Muted | No | Yes |
| Ignoring | Unmuted | No | Only standalone `listen`; others discarded |
| Ignoring | Muted | No | Only standalone `listen`; others discarded |

## Requirements and configuration

- Python 3.12 and [uv](https://docs.astral.sh/uv/getting-started/installation/).
- A Recall workspace with the LiveKit integration enabled and a REST API key.
- A LiveKit Cloud project with credentials and access to Inference for STT, LLM, and TTS.
- A Runway API key with Characters access and a character preset.
- A Google account to host the meeting.

From the repository root:

```sh
uv sync --locked
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

In the **same Recall workspace**, open **Agents → LiveKit** and configure the URL, key, and secret from the same LiveKit project. An introduction-only Agents page means the workspace still needs access to the integration.

For Runway setup, see [LiveKit's Runway guide](https://docs.livekit.io/agents/models/avatar/plugins/runway/). The app passes the preset ID to Runway while LiveKit supplies the agent's voice and instructions.

## Run

This sample's launcher currently accepts Google Meet URLs and creates `web_4_core` Google Meet bots. The agent demonstrates the Recall Output Media and LiveKit integration; the launcher validation and bot configuration would need updating to use another meeting platform.

Start the worker:

```sh
uv run --locked python -m app.agent dev
```

Wait for it to register, then start the launcher in another terminal:

```sh
uv run --locked uvicorn app.web:app --host 127.0.0.1 --port 8000
```

Keep both processes running. Open [the launcher](http://127.0.0.1:8000), create a meeting at [meet.new](https://meet.new), paste its URL, and select **Send agent**. Admit the bot if prompted. The form confirms the request was accepted; joining and avatar startup take additional time.

After the avatar connects, the bot posts:

> Start requests with 'Assistant' or 'livekit demo'. Ask questions, show a webpage, post a message/link, stop sharing, or leave. Mute/unmute controls speech; tools still work while muted. Ignore pauses all requests until 'Assistant, listen'. Listen keeps the mute setting.

An intro-chat failure does not end the session or trigger a retry. The avatar's default session limit is 10 minutes; launch another bot to repeat the demo. Restart the worker after changing code or voice settings; restart both processes after changing shared connection settings.

## Manual demonstration

1. Confirm silent joining and one chat introduction. Speak normally without either name; expect no response or action. Ask for a longer answer, then speak without either name; the answer should continue. An addressed request can interrupt once its transcript is complete.
2. Ask “Assistant, what is two plus two?” Expect a short answer without follow-up offers.
3. Say “Assistant, show https://example.com.” Check the brief delay announcement and visible screen share. Say “Assistant, send that link in chat” and check the exact URL.
4. Say “Assistant, mute and post 'Hello from the demo' in chat.” Expect both “Muted. Tools still work.” and the requested message in chat, with no speech. Repeat the mute command; it should stay muted.
5. While muted, request another webpage, its link, and then stop sharing. Prefix each request with “Assistant.” Confirm the actions work silently. Ask a question and confirm no spoken answer.
6. Say “Assistant, unmute,” check for “Unmuted.” in chat, then ask a fresh question. Expect a short answer and no replay of muted answers or actions. Repeat unmute; it should stay available.
7. Say “Assistant, ignore” and check its chat confirmation. Ask an addressed question, request a chat message, and ask it to unmute or leave. Expect no response or action. Discuss or quote “listen”; it should stay ignoring.
8. Say “Assistant, listen” as a separate request and check its chat confirmation and speech setting. Ask a fresh question and confirm a short response with no replay of ignored requests.
9. Say “Assistant, mute,” then “Assistant, ignore,” then “Assistant, listen.” It should remain silent but carry out an addressed chat request. Say “Assistant, unmute” and confirm speech returns. Repeat listen and unmute to check they preserve the state.
10. Say “Assistant, mute,” then “Assistant, leave.” Confirm that it leaves silently while your meeting stays open.

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
