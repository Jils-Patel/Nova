# Nova MVP

Multi-agent voice assistant, with a continuous back-and-forth conversation
instead of one command per hotkey press.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
   On Linux, you'll also need `mpg123` installed system-wide for audio playback
   (`sudo apt install mpg123`), `xdg-utils` for opening apps by name, and
   `python3-tk` for the Activity Log window (`sudo apt install python3-tk`).

2. Create a `.env` file in this folder with your API key and Gmail
   credentials (needed for the Email Agent - use a Gmail
   [app password](https://myaccount.google.com/apppasswords), not your
   regular account password):
   ```
   OPENAI_API_KEY=sk-...
   GMAIL_ADDRESS=you@gmail.com
   GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
   ```
   `.env` is gitignored - never commit it.

3. Run it:
   ```
   python main.py
   ```

## How to use it

- **`Ctrl+Space`** — starts a voice conversation. Talk, it replies, and it
  automatically listens again for your next turn - no need to press the
  hotkey between turns. Say "stop", "goodbye", or similar to end it, or just
  go quiet for ~12 seconds and it'll end on its own.
- The tray icon shows a colored dot: gray (idle), red (listening), amber
  (thinking), green (speaking).
- **Right-click the tray icon → "Show Activity"** to open a small,
  read-only window with a live-updating log of status changes and the
  transcript - useful for watching what's happening during a voice
  conversation without needing a terminal open. Closing it doesn't stop
  anything; it's just a viewer, reopen it anytime.
- Right-click the tray icon → Quit to exit.

## How it's structured

- `main.py` – tray icon, the hotkey, and the voice loop
- `conversation.py` – shared multi-turn conversation state
- `agents_setup.py` – the router agent and specialist agents (multi-agent handoffs)
- `tools.py` – the actual actions Nova can take (open apps, notes, calendar/
  reminders via Calendar.app and Reminders.app, etc.) - use an iCloud
  calendar/list (not "On My Mac") for events/reminders that should also
  show up on the iPhone
- `audio_io.py` – VAD-based recording (stops when you stop talking) and
  streaming TTS playback
- `chat_ui.py` – the chat-bubble rendering used by the Activity Log window
- `config.py` – model names, hotkey, and tunables, all in one place

## Tuning notes

- If voice recording cuts you off mid-sentence or keeps listening after
  you've stopped, adjust `VAD_SILENCE_THRESHOLD` in `config.py`.
- If conversations end too quickly (or not quickly enough) when you go
  quiet, adjust `CONVERSATION_TIMEOUT_S`.
- Add or change exit phrases for voice mode in `EXIT_PHRASES`.

## Extending it

- Add a new capability: write a `@function_tool` function in `tools.py`,
  then attach it to the right specialist agent in `agents_setup.py`
  (or create a new specialist entirely).
- Swap models: edit `config.py` only.
- Add wake-word detection: replace the voice hotkey trigger in `main.py`
  with a wake-word engine (e.g. Porcupine) calling `run_voice_conversation()`.