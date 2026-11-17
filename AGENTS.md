# Working on this sample

Keep this a small, runnable Google Meet demo. The page has one meeting-URL input and a submit button.

- The nine conversational tools are `show_webpage`, `send_chat_message`, `send_current_page_link`, `stop_sharing`, `leave_call`, `mute_agent`, `unmute_agent`, `ignore_agent`, and `listen_agent`.
- Require each request to start with `Assistant` or `livekit demo`. Filter other meeting conversation in the public STT node before it can interrupt or enter the agent's context. Keep `vad=None` and STT turn detection paired with this filter. Answer in one short sentence unless asked for detail; avoid unsolicited advice, follow-up questions, and spoken tool recaps.
- Start with speech enabled. `mute` silences speech only; `unmute` restores it. All requested tools remain available while muted and listening, including leaving. Never replay unheard speech or repeat actions on unmute. Repeated commands are idempotent. Gate audio in code without cancelling tool execution.
- Start listening. `ignore` stops answers and actions until a standalone addressed `listen` command. Listen/ignore preserve the mute setting. Discard ignored turns before history; never queue or replay them. Use a small exact-command check while ignoring, not a separate model classifier.
- Hardcode the meeting bot and avatar participant name as `livekit demo` in `app/config.py`. Use a female speaking voice; the example selects Rime's Astra.
- Join silently. Post one concise capabilities message in meeting chat automatically, then wait to be addressed. Do not speak a greeting or feature list. An intro chat failure must not end the session or trigger an automatic retry.
- Use LiveKit's Runway plugin (`runway.AvatarSession`) for synchronized speech and animated video. Configure its separate Runway API key and preset ID in `.env`. The demo requires a speaking avatar.
- Create Google Meet bots with `variant.google_meet` set to `web_4_core` for output media.
- Use Recall MCP documentation to check Recall API behavior. For newly released integration fields, record any documentation gap rather than guessing.
- Keep global behavior in the agent instructions, tool-specific guidance in tool docstrings, and factual outcomes in tool results.
- Let LiveKit own job shutdown; keep one explicit session-close path in `finally` for failures.
- Keep the agent lifecycle, meeting actions, and HTTP requests easy to trace. Prefer concrete names and related logic kept together. Review responsibilities when a file approaches 300 lines.
- Use the root `.env` for local configuration; never commit credentials or print them in logs. `.env.example` contains placeholders only.
- Keep the launcher bound to localhost for this demo. There is no webhook receiver or callback-verification layer.
- Do not add evaluator code, test harnesses, verification instrumentation, or reporting infrastructure to this repository. The user performs the meeting demo; verification happens outside the repository.
- Sharing a webpage does not grant the agent access to its contents. Apart from the single introductory chat message, actions require explicit participant requests. Do not automatically post links after sharing or retry uncertain actions.
- Preserve the last accepted page URL when a later share request fails. Stop sharing must keep voice available; leave must remove only the bot.
- Report what was checked and distinguish local checks from observed meeting behavior.
