"""
Chat bubble UI, built on a plain Tkinter Canvas (no extra dependencies).

Vanilla Tkinter has no native "chat bubble" widget, so this draws rounded
rectangles by hand and places wrapped text inside them - right-aligned and
one color for the user, left-aligned and another color for Nova, with
status/system lines shown as small centered dividers instead of bubbles.

Used by both the text conversation window and the Activity Log window in
main.py, so they share one visual style instead of each rolling their own.
"""

import tkinter as tk

BG = "#1a1b1e"
USER_BUBBLE = "#2f6fed"
USER_TEXT = "#ffffff"
NOVA_BUBBLE = "#2c2d31"
NOVA_TEXT = "#e8e8ea"
STATUS_TEXT = "#75787f"
TIMESTAMP_TEXT = "#5b5e64"

FONT = ("Helvetica", 12)
TIMESTAMP_FONT = ("Helvetica", 9)
STATUS_FONT = ("Helvetica", 9, "italic")

BUBBLE_MAX_WIDTH = 280
PAD_X = 12
PAD_Y = 8
RADIUS = 14
GAP_BETWEEN_MESSAGES = 10
SIDE_MARGIN = 12


class ChatView(tk.Frame):
    """A scrollable canvas that renders messages as chat bubbles."""

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("bg", BG)
        super().__init__(parent, **kwargs)

        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

        self._next_y = PAD_Y
        self._typing_ids = None
        self._typing_job = None
        self._typing_frame = 0

    def show_typing_indicator(self) -> None:
        """Show an animated dots bubble on Nova's side while a reply is
        being generated. Safe to call again while already showing - it just
        keeps animating in place rather than stacking a second one."""
        if self._typing_ids is not None:
            return  # already showing

        canvas_width = self._canvas_width()

        x1 = SIDE_MARGIN
        y1 = self._next_y
        rect_w, rect_h = 56, 32
        x2, y2 = x1 + rect_w, y1 + rect_h

        rect_id = self._draw_rounded_rect(x1, y1, x2, y2, RADIUS, fill=NOVA_BUBBLE, outline="")
        text_id = self.canvas.create_text(
            x1 + rect_w / 2, y1 + rect_h / 2, text="•",
            fill=NOVA_TEXT, font=("Helvetica", 16), anchor="center",
        )
        self._typing_ids = (rect_id, text_id)

        self.canvas.configure(scrollregion=(0, 0, canvas_width, y2 + PAD_Y))
        self.canvas.yview_moveto(1.0)

        self._animate_typing_indicator()

    def _animate_typing_indicator(self) -> None:
        if self._typing_ids is None:
            return
        frames = ["•", "• •", "• • •"]
        self._typing_frame = (self._typing_frame + 1) % len(frames)
        _, text_id = self._typing_ids
        self.canvas.itemconfig(text_id, text=frames[self._typing_frame])
        self._typing_job = self.after(450, self._animate_typing_indicator)

    def hide_typing_indicator(self) -> None:
        """Remove the typing indicator, if shown. _next_y is deliberately
        left untouched while the indicator is up, so the real reply bubble
        that follows draws in exactly the same spot - the indicator visually
        "becomes" the reply rather than leaving a gap."""
        if self._typing_job is not None:
            self.after_cancel(self._typing_job)
            self._typing_job = None

        if self._typing_ids is not None:
            for item_id in self._typing_ids:
                self.canvas.delete(item_id)
            self._typing_ids = None

    def _on_mousewheel(self, event) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta)), "units")

    def _canvas_width(self) -> int:
        self.update_idletasks()
        w = self.canvas.winfo_width()
        return w if w > 1 else 400  # fallback before the window has laid out

    def _draw_rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def add_bubble(self, text: str, align: str, timestamp: str | None = None) -> None:
        """Add a message bubble. align is 'left' (Nova) or 'right' (You)."""
        if not text:
            return

        canvas_width = self._canvas_width()
        max_text_width = min(BUBBLE_MAX_WIDTH, canvas_width - 2 * SIDE_MARGIN - 2 * PAD_X)

        bubble_color = USER_BUBBLE if align == "right" else NOVA_BUBBLE
        text_color = USER_TEXT if align == "right" else NOVA_TEXT

        # Measure by drawing off-canvas first, then position once we know the size.
        text_id = self.canvas.create_text(
            -9999, -9999, text=text, width=max_text_width, anchor="nw",
            fill=text_color, font=FONT,
        )
        bbox = self.canvas.bbox(text_id)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]

        rect_w = text_w + 2 * PAD_X
        rect_h = text_h + 2 * PAD_Y

        if align == "right":
            x2 = canvas_width - SIDE_MARGIN
            x1 = x2 - rect_w
        else:
            x1 = SIDE_MARGIN
            x2 = x1 + rect_w

        y1 = self._next_y
        y2 = y1 + rect_h

        self._draw_rounded_rect(x1, y1, x2, y2, RADIUS, fill=bubble_color, outline="")
        self.canvas.coords(text_id, x1 + PAD_X, y1 + PAD_Y)
        self.canvas.tag_raise(text_id)  # keep text visibly above the bubble shape

        self._next_y = y2 + 2

        if timestamp:
            ts_id = self.canvas.create_text(
                x2 if align == "right" else x1, self._next_y,
                text=timestamp, fill=TIMESTAMP_TEXT, font=TIMESTAMP_FONT,
                anchor="ne" if align == "right" else "nw",
            )
            ts_bbox = self.canvas.bbox(ts_id)
            self._next_y = ts_bbox[3] + GAP_BETWEEN_MESSAGES
        else:
            self._next_y += GAP_BETWEEN_MESSAGES

        self._refresh_scrollregion(canvas_width)

    def add_status(self, text: str) -> None:
        """Add a small centered status/divider line (not a bubble)."""
        if not text:
            return

        canvas_width = self._canvas_width()
        text_id = self.canvas.create_text(
            canvas_width / 2, self._next_y, text=text,
            fill=STATUS_TEXT, font=STATUS_FONT, anchor="n",
        )
        bbox = self.canvas.bbox(text_id)
        self._next_y = bbox[3] + GAP_BETWEEN_MESSAGES

        self._refresh_scrollregion(canvas_width)

    def _refresh_scrollregion(self, canvas_width: int) -> None:
        self.canvas.configure(scrollregion=(0, 0, canvas_width, self._next_y + PAD_Y))
        self.canvas.yview_moveto(1.0)  # keep pinned to the latest message

    def clear(self) -> None:
        self.canvas.delete("all")
        self._next_y = PAD_Y
        self._typing_ids = None
        self._typing_job = None