"""
Entry point. Runs a system tray icon with a global hotkey:

  Ctrl+Space  -> starts a continuous voice conversation (talk back and
                forth without re-pressing the hotkey each turn; ends when
                you say an exit phrase or go quiet for a while)

Right-click the tray icon for more options, including a read-only Activity
Log window showing status changes and the running transcript.
"""

import asyncio
import queue
import tkinter as tk

from dotenv import load_dotenv
load_dotenv()

import pystray
from PIL import Image, ImageDraw
from pynput import keyboard

import activity_log
from chat_ui import ChatView
from config import VOICE_HOTKEY, EXIT_PHRASES, CONVERSATION_TIMEOUT_S
from conversation import Conversation
from audio_io import record_audio, transcribe, speak

STATE_COLORS = {
    "idle": (120, 128, 140),         # muted slate gray
    "listening": (235, 87, 87),      # warm red
    "transcribing": (242, 153, 74),  # amber - same as thinking, just a distinct label
    "thinking": (242, 153, 74),      # amber
    "speaking": (111, 207, 151),     # soft green
}

tray_icon = None  # set in main()
_root: tk.Tk | None = None
_action_queue: "queue.Queue" = queue.Queue()


def request_window(open_func) -> None:
    """Ask the main thread to open a window. Safe to call from any thread."""
    _action_queue.put(open_func)


def _poll_actions() -> None:
    """Runs on the main thread via root.after(); drains queued window requests."""
    try:
        while True:
            action = _action_queue.get_nowait()
            action()
    except queue.Empty:
        pass
    _root.after(50, _poll_actions)


def make_icon_image(color: tuple) -> Image.Image:
    scale = 4
    size = 64 * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    margin = 6 * scale
    ring_color = tuple(max(0, c - 40) for c in color)
    draw.ellipse((margin - 3 * scale, margin - 3 * scale,
                  size - margin + 3 * scale, size - margin + 3 * scale),
                 fill=ring_color + (255,))
    draw.ellipse((margin, margin, size - margin, size - margin),
                 fill=color + (255,))

    return img.resize((64, 64), Image.LANCZOS)

def set_state(state: str) -> None:
    """Update the tray icon to reflect what Nova is currently doing."""
    if tray_icon is not None:
        tray_icon.icon = make_icon_image(STATE_COLORS[state])
        tray_icon.title = f"Nova - {state}"
    activity_log.log_event("status", state)


# --- Voice conversation ---

async def run_voice_conversation() -> None:
    conversation = Conversation()
    set_state("listening")
    print("\n--- voice conversation started ---")
    activity_log.log_event("status", "voice conversation started")

    while True:
        audio_path = record_audio(no_speech_timeout_s=CONVERSATION_TIMEOUT_S)

        if audio_path is None:
            print("--- conversation timed out (silence) ---\n")
            activity_log.log_event("status", "conversation timed out (silence)")
            break

        set_state("transcribing")
        user_text = transcribe(audio_path)
        if not user_text:
            set_state("listening")
            continue

        print(f"You: {user_text}")
        activity_log.log_event("user", user_text)

        if user_text.strip().lower().rstrip(".!?") in EXIT_PHRASES:
            set_state("speaking")
            activity_log.log_event("nova", "Goodbye.")
            speak("Goodbye.")
            break

        set_state("thinking")
        reply = await conversation.send(user_text)

        set_state("speaking")
        activity_log.log_event("nova", reply)
        speak(reply)
        set_state("listening")

    set_state("idle")


def on_voice_hotkey() -> None:
    asyncio.run(run_voice_conversation())


# --- Activity log window ---
# Read-only viewer over activity_log's rolling event buffer. Closing it just
# stops watching - it doesn't touch the conversation or the app in any way.

_activity_window_open = False  # guards against opening a second window


def open_activity_window() -> None:
    global _activity_window_open
    if _activity_window_open:
        return
    _activity_window_open = True

    win = tk.Toplevel(_root)
    win.title("Nova - Activity")
    win.geometry("460x480")
    win.configure(bg="#1a1b1e")

    chat = ChatView(win)
    chat.pack(fill="both", expand=True, padx=10, pady=10)

    def render_event(event: dict) -> None:
        if event["kind"] == "status":
            if event["text"] == "thinking":
                chat.show_typing_indicator()
            else:
                chat.hide_typing_indicator()
            chat.add_status(f"{event['text']}  ·  {event['time']}")
        elif event["kind"] == "user":
            chat.hide_typing_indicator()
            chat.add_bubble(event["text"], align="right", timestamp=event["time"])
        elif event["kind"] == "nova":
            chat.hide_typing_indicator()
            chat.add_bubble(event["text"], align="left", timestamp=event["time"])

    last_shown = 0

    def poll() -> None:
        nonlocal last_shown
        if not _activity_window_open:
            return  # window was closed since this was scheduled

        new_events, last_shown = activity_log.get_new_events(last_shown)
        for event in new_events:
            render_event(event)

        win.after(500, poll)

    poll()

    def on_close() -> None:
        global _activity_window_open
        _activity_window_open = False
        win.destroy()

    win.protocol("WM_DELETE_WINDOW", on_close)


def on_show_activity(icon, item) -> None:
    request_window(open_activity_window)


# --- Setup ---

def start_hotkey_listener() -> None:
    hotkeys = keyboard.GlobalHotKeys({
        VOICE_HOTKEY: on_voice_hotkey,
    })
    hotkeys.start()


def quit_app(icon, item) -> None:
    icon.stop()
    # Route the shutdown through the same queue as everything else, rather
    # than calling a Tk method directly from pystray's callback thread.
    request_window(_root.quit)


def _pystray_setup(icon) -> None:
    """Runs on a thread pystray manages, once the icon is registered.

    This is where "background setup that isn't Tk" goes - currently just the
    global hotkey listener.
    """
    icon.visible = True
    start_hotkey_listener()


def main() -> None:
    global tray_icon, _root

    # This hidden root is the one and only Tk mainloop for the whole app. It
    # never shows itself - it just exists so the Activity window can be a
    # Toplevel of it and get created on the main thread.
    _root = tk.Tk()
    _root.withdraw()
    _root.after(50, _poll_actions)

    menu = pystray.Menu(
        pystray.MenuItem("Show Activity", on_show_activity),
        pystray.MenuItem("Quit", quit_app),
    )
    tray_icon = pystray.Icon("nova", make_icon_image(STATE_COLORS["idle"]), "Nova - idle", menu)
    tray_icon.run_detached(setup=_pystray_setup)

    print(f"Nova is running.")
    print(f"  {VOICE_HOTKEY} -> talk (continuous conversation)")
    print("Right-click the tray icon for more options, including Show Activity.")

    _root.mainloop()


if __name__ == "__main__":
    main()