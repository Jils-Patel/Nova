# Nova MVP

Multi-agent voice assistant for macOS, with a continuous back-and-forth
conversation instead of one command per hotkey press.

Nova is Mac-only: most of its tools drive macOS apps (Safari, Calendar,
Reminders, Messages, Contacts, Keynote) through AppleScript.

## Setup

1. Install dependencies (Python 3.13):
   ```
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

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

4. Grant macOS permissions when prompted (System Settings → Privacy &
   Security) to the terminal or app you run Nova from:
   - **Microphone** - voice input
   - **Accessibility** - the global hotkey, plus clicking/typing for the
     Screen Agent
   - **Screen Recording** - screenshots for the Screen Agent
   - **Automation** - controlling Safari, Calendar, Reminders, Messages,
     Contacts, Keynote, and System Events (macOS asks once per app, the
     first time Nova uses it)

## How to use it

- **`Ctrl+Space`** — starts a voice conversation. Talk, it replies, and it
  automatically listens again for your next turn - no need to press the
  hotkey between turns. Say "stop", "goodbye", or similar to end it, or just
  go quiet for ~12 seconds and it'll end on its own. Each new conversation
  starts with no memory of the previous one.
- The tray icon shows a colored dot: gray (idle), red (listening), amber
  (thinking), green (speaking).
- **Right-click the tray icon → "Show Activity"** to open a small,
  read-only window with a live-updating log of status changes and the
  transcript - useful for watching what's happening during a voice
  conversation without needing a terminal open. Closing it doesn't stop
  anything; it's just a viewer, reopen it anytime.
- Right-click the tray icon → Quit to exit.

## What Nova can do

A router agent reads each request and hands it to one specialist:

| Agent | Handles |
|---|---|
| **Computer** | Opening/closing apps, the frontmost app, battery, system info, volume |
| **Browser** | Web search, driving Safari, and reading the current page |
| **Screen** | Screenshot-based understanding of what's on screen, plus clicking, typing, and scrolling |
| **Files** | Finding, listing, reading (text, PDF, Word), creating, and editing files; building PowerPoint decks with AI-generated images or charts, inspecting what a deck contains, and opening files |
| **Email** | Searching, reading, sending, and replying in Gmail |
| **Messages** | Sending iMessages/texts, resolving names through Contacts first |
| **Calendar** | Reading events and reminders, creating them, and completing reminders |
| **General** | Conversation and factual questions, the time, quick notes |

Email can hand off to Files (to attach or save something) or Browser (to
look something up), and both hand back to Email. Other specialists don't
hand off to each other.

Sending an email or text and creating an event or reminder always read
the draft back and wait for your spoken confirmation first.

## How it's structured

- `main.py` – tray icon, the hotkey, and the voice loop
- `conversation.py` – shared multi-turn conversation state
- `agents_setup.py` – the router agent and specialist agents (multi-agent handoffs)
- `tools.py` – the actual actions Nova can take (apps, Safari, screen,
  files and presentations, Gmail, Messages, calendar/reminders) - use an
  iCloud calendar/list (not "On My Mac") for events/reminders that should
  also show up on the iPhone
- `audio_io.py` – VAD-based recording (stops when you stop talking) and
  streaming TTS playback
- `chat_ui.py` – the chat-bubble rendering used by the Activity Log window
- `activity_log.py` – in-memory event buffer behind the Activity Log window
- `config.py` – model names, hotkey, and tunables, all in one place

## Tuning notes

- If voice recording cuts you off mid-sentence or keeps listening after
  you've stopped, adjust `VAD_SILENCE_THRESHOLD` in `config.py`.
- If conversations end too quickly (or not quickly enough) when you go
  quiet, adjust `CONVERSATION_TIMEOUT_S`.
- Add or change exit phrases for voice mode in `EXIT_PHRASES`.
- Quick notes are appended to `/tmp/nova_notes.txt`, which macOS clears on
  restart - change `TMP_NOTES_PATH` if you want them to persist.

## Extending it

- Add a new capability: write a `@function_tool` function in `tools.py`,
  then attach it to the right specialist agent in `agents_setup.py`
  (or create a new specialist entirely and add it to the router's
  `handoffs`).
- Swap models: edit `config.py` only.
- Add wake-word detection: replace the voice hotkey trigger in `main.py`
  with a wake-word engine (e.g. Porcupine) calling `run_voice_conversation()`.
