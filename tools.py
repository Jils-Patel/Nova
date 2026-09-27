"""
Local capabilities for Nova.

These functions are exposed to agents as tools. The model decides
when a capability is needed based on the tool descriptions.
"""

from __future__ import annotations

import base64
import datetime
import imaplib
import platform
import os
import smtplib
import subprocess
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from urllib.parse import quote_plus

import psutil
import pyautogui
from agents import function_tool
from openai import OpenAI

from config import (
    VISION_MODEL,
    TMP_SCREENSHOT_PATH,
    TMP_NOTES_PATH,
    IMAP_HOST,
    IMAP_PORT,
    SMTP_HOST,
    SMTP_PORT,
    EMAIL_BODY_MAX_CHARS,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _run_osascript(script: str) -> str:
    """Run AppleScript and return stdout."""
    result = subprocess.run(
        ["osascript"],
        input=script,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "AppleScript failed.")

    return result.stdout.strip()


def _home_path(path: str) -> Path:
    """Resolve a user-supplied path."""
    return Path(os.path.expanduser(path)).resolve()


def _truncate(text: str, max_chars: int = 30000) -> str:
    """Cap file content sent back to the model so a huge file can't blow
    past context limits - used by all the read_* file tools."""
    if len(text) > max_chars:
        return text[:max_chars] + "\n[File content truncated.]"
    return text


def _open_in_new_safari_tab(url: str) -> None:
    """Activate Safari (making a window first if none exists) and open a
    URL in a new tab. Shared by open_url and search_safari, which only
    differ in how they build the URL."""
    subprocess.run(["open", "-a", "Safari"], check=True)

    safe_url = url.replace("\\", "\\\\").replace('"', '\\"')

    script = f'''
    tell application "Safari"
        activate

        if (count of windows) = 0 then
            make new document
        end if

        tell window 1
            set current tab to (make new tab with properties {{URL:"{safe_url}"}})
        end tell
    end tell
    '''

    _run_osascript(script)


# ===========================================================================
# COMPUTER TOOLS
# ===========================================================================

@function_tool
def open_application(app_name: str) -> str:
    """Open an application on the user's computer.

    Use this when the user wants to launch or open an application.

    Args:
        app_name: The name of the application to open, such as
            Safari, Spotify, Notes, Finder, Terminal, or VS Code.
    """
    try:
        system = platform.system()

        if system == "Darwin":
            subprocess.run(
                ["open", "-a", app_name],
                check=True,
                capture_output=True,
                text=True,
            )
        elif system == "Windows":
            subprocess.Popen(["start", "", app_name], shell=True)
        else:
            subprocess.Popen([app_name.lower()])

        return f"Opened {app_name}."

    except Exception as e:
        return f"Couldn't open {app_name}: {e}"


@function_tool
def close_application(app_name: str) -> str:
    """Close an application that is currently running.

    Args:
        app_name: The application name, such as Safari or Spotify.
    """
    try:
        if platform.system() == "Darwin":
            _run_osascript(
                f'''
                tell application "{app_name}"
                    quit
                end tell
                '''
            )
            return f"Closed {app_name}."

        return "Closing applications is currently implemented for macOS."

    except Exception as e:
        return f"Couldn't close {app_name}: {e}"


@function_tool
def get_active_application() -> str:
    """Return the name of the application currently in the foreground."""
    try:
        script = '''
        tell application "System Events"
            name of first application process whose frontmost is true
        end tell
        '''

        app = _run_osascript(script)
        return f"The active application is {app}."

    except Exception as e:
        return f"Couldn't determine the active application: {e}"


@function_tool
def get_open_applications() -> str:
    """Return a list of currently running applications."""
    try:
        script = '''
        tell application "System Events"
            name of every application process whose background only is false
        end tell
        '''

        apps = _run_osascript(script)

        return f"Open applications: {apps}"

    except Exception as e:
        return f"Couldn't get open applications: {e}"


@function_tool
def get_battery_status() -> str:
    """Return the laptop's current battery percentage."""
    try:
        battery = psutil.sensors_battery()

        if battery is None:
            return "Battery information isn't available."

        status = "charging" if battery.power_plugged else "not charging"

        return f"Battery is at {battery.percent:.0f}% and is {status}."

    except Exception as e:
        return f"Couldn't check the battery: {e}"


@function_tool
def get_system_info() -> str:
    """Return basic information about the user's computer."""
    try:
        cpu = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()

        return (
            f"System: {platform.system()} {platform.release()}. "
            f"Processor: {platform.processor() or 'unknown'}. "
            f"CPU usage: {cpu:.0f}%. "
            f"Memory usage: {memory.percent:.0f}%."
        )

    except Exception as e:
        return f"Couldn't get system information: {e}"


@function_tool
def set_volume(volume: int) -> str:
    """Set the Mac's system volume.

    Args:
        volume: Volume percentage from 0 to 100.
    """
    volume = max(0, min(100, volume))

    try:
        _run_osascript(
            f'''
            set volume output volume {volume}
            '''
        )

        return f"Volume set to {volume}%."

    except Exception as e:
        return f"Couldn't change the volume: {e}"


@function_tool
def mute_volume() -> str:
    """Mute the Mac's system audio."""
    try:
        _run_osascript("set volume with output muted")
        return "Muted the computer."

    except Exception as e:
        return f"Couldn't mute the computer: {e}"


# ===========================================================================
# BROWSER TOOLS
# ===========================================================================

@function_tool
def open_safari() -> str:
    """Open and activate Safari."""
    try:
        subprocess.run(["open", "-a", "Safari"], check=True)

        _run_osascript(
            '''
            tell application "Safari"
                activate

                if (count of windows) = 0 then
                    make new document
                end if
            end tell
            '''
        )

        return "Safari is open."

    except Exception as e:
        return f"Couldn't open Safari: {e}"


@function_tool
def search_safari(query: str) -> str:
    """Search the web using Safari.

    Use this whenever the user wants to search the internet or look
    something up online.

    Safari is opened automatically if necessary.

    Args:
        query: What the user wants to search for.
    """
    try:
        encoded_query = quote_plus(query)
        _open_in_new_safari_tab(f"https://www.google.com/search?q={encoded_query}")

        return f'Searched the web for "{query}".'

    except Exception as e:
        return f"Couldn't search Safari: {e}"


@function_tool
def open_url(url: str) -> str:
    """Open a URL in Safari.

    Args:
        url: The complete webpage URL to open.
    """
    try:
        _open_in_new_safari_tab(url)
        return f"Opened {url}."

    except Exception as e:
        return f"Couldn't open the URL: {e}"


@function_tool
def get_current_webpage() -> str:
    """Return the title and URL of the webpage currently open in Safari."""
    try:
        script = '''
        tell application "Safari"
            if (count of windows) = 0 then
                return "NO_PAGE"
            end if

            set current_url to URL of front document
            set current_title to name of front document

            return current_title & "\\n" & current_url
        end tell
        '''

        result = _run_osascript(script)

        if result == "NO_PAGE":
            return "Safari has no open webpage."

        return result

    except Exception as e:
        return f"Couldn't inspect the current webpage: {e}"


@function_tool
def read_safari_page() -> str:
    """Read the visible text/content of the current Safari webpage.

    Use this when the user asks what is on a webpage, wants information
    extracted from the current page, or asks you to analyze webpage content.

    This reads webpage content; it does not merely return the URL.
    """
    try:
        script = '''
        tell application "Safari"
            if (count of windows) = 0 then
                return "Safari has no open window."
            end if

            try
                set page_text to do JavaScript "document.body.innerText" in front document
                return page_text
            on error
                return text of front document
            end try
        end tell
        '''

        text = _run_osascript(script)

        if not text:
            return "The webpage did not contain readable text."

        # Keep enormous webpages from flooding the model context.
        max_chars = 30000

        if len(text) > max_chars:
            text = text[:max_chars] + "\n[Page content truncated.]"

        return text

    except Exception as e:
        return (
            "Couldn't read the Safari page. "
            "On macOS, Safari may need permission for automation/JavaScript. "
            f"Technical error: {e}"
        )


@function_tool
def go_back_in_safari() -> str:
    """Navigate Safari back one page."""
    try:
        _run_osascript(
            '''
            tell application "Safari"
                activate
                go back in front document
            end tell
            '''
        )
        return "Went back one page."

    except Exception as e:
        return f"Couldn't go back: {e}"


@function_tool
def go_forward_in_safari() -> str:
    """Navigate Safari forward one page."""
    try:
        _run_osascript(
            '''
            tell application "Safari"
                activate
                go forward in front document
            end tell
            '''
        )
        return "Went forward one page."

    except Exception as e:
        return f"Couldn't go forward: {e}"


@function_tool
def refresh_safari() -> str:
    """Refresh the current Safari webpage."""
    try:
        _run_osascript(
            '''
            tell application "Safari"
                activate
                do JavaScript "location.reload()" in front document
            end tell
            '''
        )

        return "Refreshed the page."

    except Exception as e:
        return f"Couldn't refresh Safari: {e}"


# ===========================================================================
# SCREEN TOOLS
# ===========================================================================

@function_tool
def analyze_screen(question: str) -> str:
    """Look at the current computer screen and answer a visual question.

    Use this when the user wants Nova to understand something visually
    displayed on the screen.

    Args:
        question: What you want to understand about the current screen.
    """
    screenshot_path = TMP_SCREENSHOT_PATH

    try:
        if platform.system() != "Darwin":
            return "Screen analysis is currently implemented for macOS."

        subprocess.run(
            ["screencapture", "-x", screenshot_path],
            check=True,
        )

        with open(screenshot_path, "rb") as image_file:
            image_b64 = base64.b64encode(image_file.read()).decode("utf-8")

        client = OpenAI()

        response = client.responses.create(
            model=VISION_MODEL,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Analyze this screenshot and answer the user's "
                                f"question accurately.\n\nQuestion: {question}"
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": (
                                f"data:image/png;base64,{image_b64}"
                            ),
                            "detail": "high",
                        },
                    ],
                }
            ],
        )

        return response.output_text

    except Exception as e:
        return f"Couldn't analyze the screen: {e}"


@function_tool
def click_screen(x: int, y: int) -> str:
    """Click a location on the user's screen.

    Use this only when the exact screen coordinates are known.

    Args:
        x: Horizontal screen coordinate.
        y: Vertical screen coordinate.
    """
    try:
        pyautogui.click(x, y)
        return f"Clicked at ({x}, {y})."

    except Exception as e:
        return f"Couldn't click the screen: {e}"


@function_tool
def type_on_screen(text: str) -> str:
    """Type text into the currently focused application.

    Args:
        text: The text to type.
    """
    try:
        pyautogui.write(text, interval=0.01)
        return "Typed the requested text."

    except Exception as e:
        return f"Couldn't type the text: {e}"


@function_tool
def scroll_screen(amount: int) -> str:
    """Scroll the current screen.

    Args:
        amount: Positive scrolls up; negative scrolls down.
    """
    try:
        pyautogui.scroll(amount)
        return "Scrolled the screen."

    except Exception as e:
        return f"Couldn't scroll: {e}"


# ===========================================================================
# FILE TOOLS
# ===========================================================================

@function_tool
def find_file(filename: str, search_directory: str = "~") -> str:
    """Find files on the user's computer by filename.

    Args:
        filename: Full or partial filename to search for.
        search_directory: Directory where the search should begin.
    """
    root = _home_path(search_directory)

    if not root.exists():
        return f"Directory does not exist: {root}"

    matches = []

    try:
        for path in root.rglob("*"):
            if path.is_file() and filename.lower() in path.name.lower():
                matches.append(str(path))

                if len(matches) >= 20:
                    break

        if not matches:
            return f"No files matching '{filename}' were found."

        return "Found:\n" + "\n".join(matches)

    except Exception as e:
        return f"Couldn't search for files: {e}"


@function_tool
def list_folder(directory: str = "~") -> str:
    """List the contents of a folder.

    Args:
        directory: Folder path to inspect.
    """
    path = _home_path(directory)

    try:
        if not path.exists():
            return f"Directory does not exist: {path}"

        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))

        if not entries:
            return "The folder is empty."

        lines = []

        for entry in entries[:100]:
            prefix = "[DIR]" if entry.is_dir() else "[FILE]"
            lines.append(f"{prefix} {entry.name}")

        return "\n".join(lines)

    except Exception as e:
        return f"Couldn't list the folder: {e}"


@function_tool
def read_file(path: str) -> str:
    """Read a text file from the user's computer.

    Use this for text-based files such as TXT, MD, JSON, CSV, Python,
    JavaScript, YAML, and similar files. For PDF files use read_pdf, and
    for Word documents (.docx) use read_docx.

    Args:
        path: Path to the file.
    """
    file_path = _home_path(path)

    try:
        if not file_path.exists():
            return f"File does not exist: {file_path}"

        if not file_path.is_file():
            return f"That path is not a file: {file_path}"

        text = file_path.read_text(errors="replace")
        return _truncate(text)

    except Exception as e:
        return f"Couldn't read the file: {e}"


@function_tool
def read_pdf(path: str) -> str:
    """Read the text content of a PDF file.

    Args:
        path: Path to the PDF file.
    """
    file_path = _home_path(path)

    try:
        if not file_path.exists():
            return f"File does not exist: {file_path}"

        if file_path.suffix.lower() != ".pdf":
            return f"That doesn't look like a PDF file: {file_path}"

        from pypdf import PdfReader

        reader = PdfReader(str(file_path))

        if reader.is_encrypted:
            # is_encrypted is True even for PDFs that only restrict printing/
            # editing but have no actual open password - try an empty
            # password before giving up, since that covers most of those.
            from pypdf import PasswordType

            result = reader.decrypt("")
            if result == PasswordType.NOT_DECRYPTED:
                return f"That PDF is password-protected and can't be read: {file_path}"

        pages_text = []
        for page in reader.pages:
            pages_text.append(page.extract_text() or "")

        text = "\n\n".join(pages_text).strip()

        if not text:
            return (
                f"No extractable text found in {file_path.name} - it may be a "
                "scanned/image-only PDF, which isn't supported yet."
            )

        return _truncate(text)

    except Exception as e:
        return f"Couldn't read the PDF: {e}"


@function_tool
def read_docx(path: str) -> str:
    """Read the text content of a Word document (.docx).

    Args:
        path: Path to the .docx file.
    """
    file_path = _home_path(path)

    try:
        if not file_path.exists():
            return f"File does not exist: {file_path}"

        if file_path.suffix.lower() != ".docx":
            return f"That doesn't look like a Word (.docx) file: {file_path}"

        import docx

        document = docx.Document(str(file_path))
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]

        # Tables aren't picked up by document.paragraphs - read them too.
        for table in document.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells)
                if row_text.strip(" |"):
                    paragraphs.append(row_text)

        text = "\n".join(paragraphs).strip()

        if not text:
            return f"No readable text found in {file_path.name}."

        return _truncate(text)

    except Exception as e:
        return f"Couldn't read the Word document: {e}"


@function_tool
def create_file(path: str, content: str) -> str:
    """Create a new text file.

    Args:
        path: Where the file should be created.
        content: The text content of the file.
    """
    file_path = _home_path(path)

    try:
        if file_path.exists():
            return f"That file already exists: {file_path}"

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)

        return f"Created {file_path}."

    except Exception as e:
        return f"Couldn't create the file: {e}"


@function_tool
def write_file(path: str, content: str) -> str:
    """Replace the contents of an existing text file.

    Args:
        path: Path to the file.
        content: Complete new contents of the file.
    """
    file_path = _home_path(path)

    try:
        if not file_path.exists():
            return f"File does not exist: {file_path}"

        file_path.write_text(content)

        return f"Updated {file_path}."

    except Exception as e:
        return f"Couldn't update the file: {e}"


@function_tool
def create_presentation(path: str, title: str, subtitle: str, slides_json: str) -> str:
    """Create a nicely designed PowerPoint (.pptx) deck, optionally with
    AI-generated images or native charts on individual slides.

    Build the outline yourself before calling this - a short, punchy title
    slide plus one slide per key point, each with a heading and 2-5 short
    bullets (not long paragraphs). Add a visual to a slide only when it
    would genuinely help - a relevant image for a concept/story slide, or a
    chart for anything with real numbers to compare. Don't add one to every
    slide.

    Args:
        path: Where to save the deck, e.g. "~/Desktop/Q3 Roadmap.pptx".
        title: Title shown on the title slide.
        subtitle: Subtitle/byline shown under the title (can be empty).
        slides_json: JSON array of content slides, each shaped like
            {"heading": "Slide heading", "bullets": ["point one", "point two"],
            "image_prompt": "optional description of an image to generate for this slide",
            "chart": {"type": "bar" | "line" | "pie", "categories": ["A", "B"], "series_name": "Sales", "values": [1, 2]}}.
            image_prompt and chart are both optional and mutually exclusive per slide.
    """
    file_path = _home_path(path)

    try:
        if file_path.suffix.lower() != ".pptx":
            file_path = file_path.with_suffix(".pptx")

        import base64
        import json
        import shutil
        import tempfile

        from pptx import Presentation
        from pptx.chart.data import CategoryChartData
        from pptx.dml.color import RGBColor
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
        from pptx.enum.text import PP_ALIGN
        from pptx.util import Emu, Pt

        try:
            slides_data = json.loads(slides_json)
        except json.JSONDecodeError as e:
            return f"slides_json wasn't valid JSON: {e}"

        if not isinstance(slides_data, list) or not slides_data:
            return "slides_json must be a non-empty list of {heading, bullets} slides."

        # Simple, cohesive dark-navy / gold theme applied to every slide.
        BG = RGBColor(0x0F, 0x17, 0x2A)
        ACCENT = RGBColor(0xD4, 0xAF, 0x6A)
        TEXT = RGBColor(0xF2, 0xF3, 0xF5)
        MUTED = RGBColor(0xA9, 0xB2, 0xC3)
        FONT = "Helvetica Neue"

        CHART_TYPES = {
            "bar": XL_CHART_TYPE.COLUMN_CLUSTERED,
            "line": XL_CHART_TYPE.LINE_MARKERS,
            "pie": XL_CHART_TYPE.PIE,
        }

        prs = Presentation()
        prs.slide_width = Emu(12192000)   # 16:9, 13.33in
        prs.slide_height = Emu(6858000)   # 7.5in
        blank_layout = prs.slide_layouts[6]

        tmp_dir = Path(tempfile.mkdtemp(prefix="nova_slides_"))
        image_client = None  # lazily created only if a slide actually needs one
        images_added = 0
        image_errors = []

        def add_background(slide):
            fill = slide.background.fill
            fill.solid()
            fill.fore_color.rgb = BG

        def add_accent_bar(slide):
            bar = slide.shapes.add_shape(1, Emu(0), Emu(0), Emu(160000), prs.slide_height)
            bar.fill.solid()
            bar.fill.fore_color.rgb = ACCENT
            bar.line.fill.background()
            bar.shadow.inherit = False

        def add_textbox(slide, left, top, width, height):
            box = slide.shapes.add_textbox(Emu(left), Emu(top), Emu(width), Emu(height))
            box.text_frame.word_wrap = True
            return box.text_frame

        def generate_image(prompt: str) -> Path | None:
            nonlocal image_client
            try:
                if image_client is None:
                    image_client = OpenAI()

                result = image_client.images.generate(
                    model="gpt-image-2.5-flare",
                    prompt=prompt,
                    size="1024x1024",
                    quality="low",
                )
                image_bytes = base64.b64decode(result.data[0].b64_json)

                image_path = tmp_dir / f"img_{len(list(tmp_dir.glob('img_*')))}.png"
                image_path.write_bytes(image_bytes)
                return image_path

            except Exception as e:
                # Visual is a bonus - fall back to a text-only slide, but
                # remember why so the result doesn't overstate what landed.
                image_errors.append(str(e))
                return None

        def add_chart(slide, chart_info, left, top, width, height):
            chart_type = CHART_TYPES.get(str(chart_info.get("type", "bar")).lower())
            if chart_type is None:
                return

            categories = chart_info.get("categories") or []
            values = chart_info.get("values") or []
            series_name = chart_info.get("series_name") or "Series 1"
            if not categories or not values:
                return

            chart_data = CategoryChartData()
            chart_data.categories = categories
            chart_data.add_series(series_name, values)

            graphic_frame = slide.shapes.add_chart(
                chart_type, Emu(left), Emu(top), Emu(width), Emu(height), chart_data
            )
            chart = graphic_frame.chart
            chart.has_legend = chart_type == XL_CHART_TYPE.PIE
            if chart.has_legend:
                chart.legend.position = XL_LEGEND_POSITION.BOTTOM
                chart.legend.include_in_layout = False

            plot = chart.plots[0]
            plot.has_data_labels = True

            for series in plot.series:
                series.format.fill.solid()
                series.format.fill.fore_color.rgb = ACCENT

        # --- Title slide -----------------------------------------------
        title_slide = prs.slides.add_slide(blank_layout)
        add_background(title_slide)
        add_accent_bar(title_slide)

        tf = add_textbox(title_slide, 900000, 2700000, 10400000, 1500000)
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(44)
        p.font.bold = True
        p.font.color.rgb = TEXT
        p.font.name = FONT
        p.alignment = PP_ALIGN.LEFT

        if subtitle:
            tf2 = add_textbox(title_slide, 900000, 4000000, 10400000, 700000)
            p2 = tf2.paragraphs[0]
            p2.text = subtitle
            p2.font.size = Pt(20)
            p2.font.color.rgb = MUTED
            p2.font.name = FONT

        # --- Content slides ----------------------------------------------
        for slide_info in slides_data:
            heading = str(slide_info.get("heading", "")).strip()
            bullets = slide_info.get("bullets", [])
            image_prompt = slide_info.get("image_prompt")
            chart_info = slide_info.get("chart")

            slide = prs.slides.add_slide(blank_layout)
            add_background(slide)
            add_accent_bar(slide)

            head_tf = add_textbox(slide, 900000, 500000, 10400000, 900000)
            hp = head_tf.paragraphs[0]
            hp.text = heading
            hp.font.size = Pt(30)
            hp.font.bold = True
            hp.font.color.rgb = TEXT
            hp.font.name = FONT

            # A visual (image or chart) takes the right half; text narrows
            # to the left half to make room. Otherwise text spans the slide.
            has_visual = bool(image_prompt) or bool(chart_info)
            body_width = 5300000 if has_visual else 10200000

            body_tf = add_textbox(slide, 950000, 1700000, body_width, 4700000)
            for i, bullet in enumerate(bullets):
                bp = body_tf.paragraphs[0] if i == 0 else body_tf.add_paragraph()
                bp.text = f"›  {bullet}"
                bp.font.size = Pt(20)
                bp.font.color.rgb = TEXT
                bp.font.name = FONT
                bp.space_after = Pt(16)

            if chart_info:
                add_chart(slide, chart_info, 6500000, 1700000, 5100000, 4400000)

            elif image_prompt:
                image_path = generate_image(image_prompt)
                if image_path is not None:
                    slide.shapes.add_picture(
                        str(image_path), Emu(6500000), Emu(1700000),
                        width=Emu(5100000), height=Emu(4400000),
                    )
                    images_added += 1

        file_path.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(file_path))
        shutil.rmtree(tmp_dir, ignore_errors=True)

        result = f"Created the presentation at {file_path} with {len(slides_data) + 1} slides"
        if images_added or image_errors:
            result += f" and {images_added} embedded image(s)"
        result += "."
        if image_errors:
            result += (
                f" {len(image_errors)} image(s) failed to generate and those "
                f"slides are text-only. First error: {image_errors[0]}"
            )
        return result

    except Exception as e:
        return f"Couldn't create the presentation: {e}"


@function_tool
def inspect_presentation(path: str) -> str:
    """Report what's actually inside a PowerPoint (.pptx) file, slide by
    slide: heading, number of bullets, and any embedded images or charts.

    Use this - not a screenshot - to check whether a deck contains images,
    charts, or particular content. An app window can show an out-of-date
    copy; this reads the file on disk.

    Args:
        path: Path to the .pptx file.
    """
    file_path = _home_path(path)

    try:
        if not file_path.exists():
            return f"File does not exist: {file_path}"

        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE

        prs = Presentation(str(file_path))
        lines = []
        total_images = 0
        total_charts = 0

        for i, slide in enumerate(prs.slides, start=1):
            texts = [
                shape.text_frame.text.strip()
                for shape in slide.shapes
                if shape.has_text_frame and shape.text_frame.text.strip()
            ]
            images = sum(1 for shape in slide.shapes if shape.shape_type == MSO_SHAPE_TYPE.PICTURE)
            charts = sum(1 for shape in slide.shapes if getattr(shape, "has_chart", False))
            total_images += images
            total_charts += charts

            heading = texts[0].splitlines()[0] if texts else "(no text)"
            bullets = sum(len(t.splitlines()) for t in texts[1:])
            lines.append(
                f"Slide {i}: {heading} - {bullets} bullet(s), "
                f"{images} image(s), {charts} chart(s)"
            )

        summary = (
            f"{file_path.name}: {len(prs.slides)} slides, "
            f"{total_images} embedded image(s), {total_charts} chart(s)."
        )
        return summary + "\n" + "\n".join(lines)

    except Exception as e:
        return f"Couldn't inspect the presentation: {e}"


def _close_stale_keynote_copy(file_path: Path) -> str | None:
    """If Keynote already has this deck open, close that copy so `open`
    re-imports the current file from disk instead of just re-focusing an
    out-of-date window. Returns a message if it was left open because it
    has unsaved changes."""
    names = [file_path.name, file_path.stem]
    conditions = " or ".join(
        'name is "' + n.replace("\\", "\\\\").replace('"', '\\"') + '"' for n in names
    )

    script = f"""
    if application "Keynote" is running then
        tell application "Keynote"
            set matches to (every document whose {conditions})
            repeat with d in matches
                if modified of d then return "modified"
            end repeat
            repeat with d in matches
                close d saving no
            end repeat
        end tell
    end if
    return "ok"
    """

    if _run_osascript(script) == "modified":
        return (
            f"Keynote already has {file_path.name} open with unsaved changes, "
            "so it may be showing an older version. Ask the user whether to "
            "close it without saving so the latest file can be reopened."
        )
    return None


@function_tool
def open_file(path: str) -> str:
    """Open a file using the user's default Mac application.

    Args:
        path: Path to the file to open.
    """
    file_path = _home_path(path)

    try:
        if not file_path.exists():
            return f"File does not exist: {file_path}"

        if file_path.suffix.lower() in (".pptx", ".ppt", ".key"):
            warning = _close_stale_keynote_copy(file_path)
            if warning:
                return warning

        subprocess.run(["open", str(file_path)], check=True)

        return f"Opened {file_path.name}."

    except Exception as e:
        return f"Couldn't open the file: {e}"


# ===========================================================================
# GENERAL / INFORMATION TOOLS
# ===========================================================================

@function_tool
def get_current_time() -> str:
    """Return the user's current local date and time."""
    now = datetime.datetime.now()
    return now.strftime("It's %I:%M %p on %A, %B %d, %Y.")


@function_tool
def create_note(content: str) -> str:
    """Save a quick note for the user.

    Args:
        content: The note content.
    """
    note_path = Path(TMP_NOTES_PATH)

    try:
        with note_path.open("a") as f:
            f.write(
                f"{datetime.datetime.now().isoformat()}: {content}\n"
            )

        return "Saved the note."

    except Exception as e:
        return f"Couldn't save the note: {e}"


# ===========================================================================
# EMAIL TOOLS
# ===========================================================================
#
# Gmail over IMAP (reading/searching) and SMTP (sending) - stdlib only, no
# new dependencies. Auth is a Gmail "app password" (not the account
# password), read from the environment at call time so it's never
# hardcoded or logged:
#
#   GMAIL_ADDRESS       - the Gmail address Nova reads/sends as
#   GMAIL_APP_PASSWORD  - a Gmail app password
#
# search_emails/read_email deliberately return plain-text summaries, never
# raw MIME, so the model doesn't have to parse email internals and replies
# stay short enough to be spoken aloud.
#
# reply_to_email() depends on read_email() having been called earlier -
# it threads off whichever message read_email most recently returned.
# That's in-memory, per-process state (not per-conversation), so it
# reflects the single most recently read email across whichever
# conversation - voice or text - touched it last.

_last_read_email: dict | None = None


def _gmail_credentials() -> tuple[str, str]:
    address = os.getenv("GMAIL_ADDRESS")
    app_password = os.getenv("GMAIL_APP_PASSWORD")

    if not address or not app_password:
        raise RuntimeError(
            "GMAIL_ADDRESS and/or GMAIL_APP_PASSWORD aren't set - add them "
            "to .env."
        )

    return address, app_password


def _imap_connect() -> imaplib.IMAP4_SSL:
    address, app_password = _gmail_credentials()
    imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    imap.login(address, app_password)
    imap.select("INBOX")
    return imap


def _smtp_connect() -> smtplib.SMTP_SSL:
    address, app_password = _gmail_credentials()
    smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
    smtp.login(address, app_password)
    return smtp


def _decode_header_value(value: str | None) -> str:
    """Decode a MIME-encoded header (e.g. '=?UTF-8?B?...?=') into plain
    text. Falls back to the raw value if it isn't encoded."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _gmail_search(imap: imaplib.IMAP4_SSL, query: str) -> list[bytes]:
    """Run a Gmail-syntax search (the X-GM-RAW IMAP extension) and return
    matching UIDs, most recent first."""
    safe_query = query.replace("\\", "\\\\").replace('"', '\\"')
    typ, data = imap.uid("search", None, "X-GM-RAW", f'"{safe_query}"')

    if typ != "OK" or not data or not data[0]:
        return []

    return list(reversed(data[0].split()))


def _fetch_message(imap: imaplib.IMAP4_SSL, uid: bytes):
    """Fetch and parse one message by UID."""
    typ, data = imap.uid("fetch", uid, "(RFC822)")

    if typ != "OK" or not data or not data[0]:
        raise RuntimeError("Couldn't fetch that message.")

    return message_from_bytes(data[0][1])


def _plain_text_body(msg) -> str:
    """Pull the plain-text body out of a (possibly multipart) message."""
    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get("Content-Disposition") or "")

            if part.get_content_type() == "text/plain" and "attachment" not in disposition:
                try:
                    return part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    continue
        return ""

    try:
        return msg.get_payload(decode=True).decode(
            msg.get_content_charset() or "utf-8", errors="replace"
        )
    except Exception:
        return str(msg.get_payload())


@function_tool
def search_emails(query: str, max_results: int = 5) -> str:
    """Search the user's Gmail inbox.

    Returns short summaries only (sender, subject, date, a one-line
    snippet) - use read_email to get a full message body.

    Args:
        query: A Gmail search query - accepts real Gmail search syntax,
            e.g. "from:sarah is:unread", "subject:invoice",
            "newer_than:2d".
        max_results: Maximum number of results to return.
    """
    try:
        imap = _imap_connect()

        try:
            uids = _gmail_search(imap, query)[:max_results]

            if not uids:
                return f"No emails matched '{query}'."

            lines = []
            for uid in uids:
                msg = _fetch_message(imap, uid)

                sender = _decode_header_value(msg.get("From", "unknown sender"))
                subject = _decode_header_value(msg.get("Subject", "(no subject)"))
                date = msg.get("Date", "unknown date")
                snippet = _plain_text_body(msg).strip().replace("\n", " ")[:140]

                lines.append(f"From: {sender} | Subject: {subject} | {date}\n  {snippet}")

            return "\n".join(lines)

        finally:
            imap.logout()

    except Exception as e:
        return f"Couldn't search email: {e}"


@function_tool
def read_email(identifier: str) -> str:
    """Read the full content of one email.

    Also remembers this message so a follow-up reply_to_email call threads
    correctly.

    Args:
        identifier: A description of which email to read - e.g. a sender
            name, a subject, or "the most recent email" / "the newest
            unread email". Used as a Gmail search; the best (most recent)
            match is read.
    """
    global _last_read_email

    try:
        imap = _imap_connect()

        try:
            is_most_recent = identifier.strip().lower() in {
                "the most recent email", "most recent email", "most recent",
                "the newest email", "newest email", "newest", "latest email", "latest",
            }
            query = "in:inbox" if is_most_recent else identifier
            uids = _gmail_search(imap, query)

            if not uids:
                return f"Couldn't find an email matching '{identifier}'."

            msg = _fetch_message(imap, uids[0])

            sender = _decode_header_value(msg.get("From", "unknown sender"))
            subject = _decode_header_value(msg.get("Subject", "(no subject)"))
            date = msg.get("Date", "unknown date")
            body = _plain_text_body(msg).strip()

            if len(body) > EMAIL_BODY_MAX_CHARS:
                body = body[:EMAIL_BODY_MAX_CHARS] + "\n[Email content truncated.]"

            _last_read_email = {
                "message_id": msg.get("Message-ID", ""),
                "references": msg.get("References", ""),
                "reply_to_address": parseaddr(msg.get("Reply-To") or msg.get("From", ""))[1],
                "subject": subject,
            }

            return f"From: {sender}\nSubject: {subject}\nDate: {date}\n\n{body}"

        finally:
            imap.logout()

    except Exception as e:
        return f"Couldn't read that email: {e}"


@function_tool
def send_email(to: str, subject: str, body: str) -> str:
    """Compose and send a new email.

    Only call this after reading the composed message back to the user and
    getting their explicit confirmation to send it, in this same turn -
    this tool sends immediately with no built-in pause of its own.

    Args:
        to: Recipient email address.
        subject: Subject line.
        body: Email body text.
    """
    try:
        address, _ = _gmail_credentials()

        msg = EmailMessage()
        msg["From"] = address
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        smtp = _smtp_connect()
        try:
            smtp.send_message(msg)
        finally:
            smtp.quit()

        return f"Sent email to {to}."

    except Exception as e:
        return f"Couldn't send the email: {e}"


@function_tool
def reply_to_email(body: str) -> str:
    """Reply to whichever email read_email most recently returned, carrying
    forward the right headers so it threads correctly in the recipient's
    inbox instead of showing up as a new, unrelated message.

    Only call this after reading the composed reply back to the user and
    getting their explicit confirmation to send it, in this same turn -
    this tool sends immediately with no built-in pause of its own.

    Args:
        body: The reply body text.
    """
    if _last_read_email is None:
        return "No email has been read yet - use read_email first, then reply_to_email."

    try:
        address, _ = _gmail_credentials()
        original = _last_read_email

        if not original["reply_to_address"]:
            return "Couldn't determine who to reply to."

        subject = original["subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        references = " ".join(
            part for part in [original["references"], original["message_id"]] if part
        )

        msg = EmailMessage()
        msg["From"] = address
        msg["To"] = original["reply_to_address"]
        msg["Subject"] = subject
        if original["message_id"]:
            msg["In-Reply-To"] = original["message_id"]
        if references:
            msg["References"] = references
        msg.set_content(body)

        smtp = _smtp_connect()
        try:
            smtp.send_message(msg)
        finally:
            smtp.quit()

        return f"Sent reply to {original['reply_to_address']}."

    except Exception as e:
        return f"Couldn't send the reply: {e}"


# ===========================================================================
# MESSAGES TOOLS
# ===========================================================================

def _is_handle(text: str) -> bool:
    """Rough check for whether text already looks like a phone number or
    email address, rather than a display name that needs resolving."""
    text = text.strip()
    if "@" in text:
        return True
    digits = sum(c.isdigit() for c in text)
    return digits >= 7  # phone numbers; a bare name won't have this many digits


@function_tool
def find_contact_handle(name: str) -> str:
    """Look up a person in the user's Contacts app and return their phone
    numbers and emails.

    Always call this first when the user names a person (rather than
    giving a phone number or email directly) before sending a message -
    do not pass a bare name straight to send_message, since matching a
    name against Messages' own buddy list can silently match the wrong
    person or create a new, unrelated recipient instead of failing.

    If this returns more than one match (either multiple people, or
    multiple numbers/emails for the same person), ask the user which one
    they mean before calling send_message. If it returns no matches, ask
    the user for a phone number or email address directly.

    Args:
        name: The contact's name, as the user said it.
    """
    try:
        # Pull every contact's name/nickname/phones/emails and filter in
        # Python rather than using AppleScript's "whose ... contains" -
        # `name` is a computed property on Contacts' person objects, and
        # `whose` filtering against computed properties is unreliable and
        # can silently return zero matches even when the contact exists.
        script = '''
        set output to ""
        tell application "Contacts"
            repeat with p in every person
                set personName to name of p
                try
                    set nick to nickname of p
                on error
                    set nick to ""
                end try
                repeat with ph in phones of p
                    set output to output & personName & "|" & nick & "|phone|" & (value of ph) & "\\n"
                end repeat
                repeat with em in emails of p
                    set output to output & personName & "|" & nick & "|email|" & (value of em) & "\\n"
                end repeat
            end repeat
        end tell
        return output
        '''

        raw = _run_osascript(script)
        lines = [line for line in raw.splitlines() if line.strip()]

        if not lines:
            return (
                "Contacts returned no entries at all, which usually means "
                "this app doesn't have permission to control Contacts yet. "
                "Check System Settings > Privacy & Security > Automation "
                "and make sure Contacts is allowed there, then try again."
            )

        query = name.strip().lower()
        matches = []
        for line in lines:
            parts = line.split("|", 3)
            if len(parts) != 4:
                continue
            contact_name, nickname, kind, value = parts
            if query in contact_name.lower() or (nickname and query in nickname.lower()):
                matches.append((contact_name, nickname, kind, value))

        if not matches:
            return f"No contact matching '{name}' was found among {len(lines)} contact entries."

        formatted_lines = []
        for contact_name, nickname, kind, value in matches:
            label = f"{contact_name} ({nickname})" if nickname else contact_name
            formatted_lines.append(f"- {label} — {kind}: {value}")

        return f"Found the following for '{name}':\n" + "\n".join(formatted_lines)

    except Exception as e:
        return f"Couldn't look up '{name}' in Contacts: {e}"


@function_tool
def send_message(recipient: str, body: str) -> str:
    """Send an iMessage or text message via the Messages app.

    IMPORTANT: recipient must be an exact phone number or email address,
    not a bare display name - if the user named a person, call
    find_contact_handle first to resolve them to a real phone number or
    email, and confirm the resolved contact with the user, before calling
    this. Passing a bare name here relies on Messages' own fuzzy name
    matching, which can silently match the wrong person or send to a new,
    unrelated recipient instead of failing loudly.

    Only call this after reading the composed message back to the user -
    including which resolved contact/handle it's going to - and getting
    their explicit confirmation to send it, in this same turn. This tool
    sends immediately with no built-in pause of its own.

    Args:
        recipient: An exact phone number or email address to send to.
        body: The message text to send.
    """
    try:
        safe_recipient = recipient.replace("\\", "\\\\").replace('"', '\\"')
        safe_body = body.replace("\\", "\\\\").replace('"', '\\"')

        script = f'''
        tell application "Messages"
            set targetService to id of 1st service whose service type = iMessage
            set targetBuddy to buddy "{safe_recipient}" of service id targetService
            send "{safe_body}" to targetBuddy
            return (handle of targetBuddy)
        end tell
        '''

        resolved_handle = _run_osascript(script)

        if resolved_handle and resolved_handle.strip() != recipient.strip():
            return (
                f"Warning: asked to send to {recipient}, but Messages resolved "
                f"this to a different handle ({resolved_handle}). The message "
                f"may have gone to the wrong person - please double check."
            )

        return f"Sent message to {recipient}."

    except Exception as e:
        return (
            f"Couldn't send the message to {recipient}: {e}. "
            "Try a phone number or email address if this hasn't been resolved yet."
        )


# ===========================================================================
# CALENDAR & REMINDERS TOOLS
# ===========================================================================
#
# Calendar.app and Reminders.app, driven via AppleScript. Events/reminders
# created here land wherever `calendar_name`/`list_name` points - use an
# iCloud calendar/list (not a local "On My Mac" one) if they should also
# show up on the user's iPhone, since that sync is handled entirely by
# iCloud, not by Nova.

def _parse_datetime(value: str) -> datetime.datetime:
    """Parse a 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD' string."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Couldn't parse date/time: {value!r} (expected 'YYYY-MM-DD HH:MM')")


def _applescript_date_block(var_name: str, dt: datetime.datetime) -> str:
    """AppleScript statements that build a `date` value with the given
    components, assigned to var_name. Building dates this way (rather than
    parsing an ISO string) is the reliable approach in AppleScript, whose
    date parsing is locale-dependent."""
    return f'''
    set {var_name} to current date
    set year of {var_name} to {dt.year}
    set month of {var_name} to {dt.month}
    set day of {var_name} to {dt.day}
    set hours of {var_name} to {dt.hour}
    set minutes of {var_name} to {dt.minute}
    set seconds of {var_name} to 0
    '''


def _escape_as(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


@function_tool
def get_calendar_events(start_date: str, end_date: str = "", calendar_name: str = "") -> str:
    """List calendar events in a date range.

    Args:
        start_date: Start of the range, as 'YYYY-MM-DD'.
        end_date: End of the range (inclusive), as 'YYYY-MM-DD'. Defaults to
            the same day as start_date if omitted.
        calendar_name: Only look in this specific calendar. Leave empty to
            search every calendar.
    """
    try:
        start_dt = _parse_datetime(start_date)
        end_dt = _parse_datetime(end_date) if end_date else start_dt
        # Inclusive end-of-day.
        end_dt = end_dt.replace(hour=23, minute=59)

        calendar_filter = (
            f'calendars whose name is "{_escape_as(calendar_name)}"'
            if calendar_name else "calendars"
        )

        script = f'''
        set output to ""
        {_applescript_date_block("rangeStart", start_dt)}
        {_applescript_date_block("rangeEnd", end_dt)}
        tell application "Calendar"
            repeat with cal in ({calendar_filter})
                repeat with evt in (every event of cal whose start date is greater than or equal to rangeStart and start date is less than or equal to rangeEnd)
                    set output to output & (summary of evt) & "|" & ((start date of evt) as string) & "|" & ((end date of evt) as string) & "|" & (name of cal) & "\\n"
                end repeat
            end repeat
        end tell
        return output
        '''

        raw = _run_osascript(script)
        lines = [line for line in raw.splitlines() if line.strip()]

        if not lines:
            return f"No events found between {start_date} and {end_date or start_date}."

        formatted = []
        for line in lines:
            parts = line.split("|", 3)
            if len(parts) != 4:
                continue
            title, evt_start, evt_end, cal = parts
            formatted.append(f"- {title} ({cal}): {evt_start} to {evt_end}")

        return "\n".join(formatted)

    except Exception as e:
        return f"Couldn't get calendar events: {e}"


@function_tool
def create_event(
    title: str,
    start_datetime: str,
    end_datetime: str,
    calendar_name: str = "",
    location: str = "",
) -> str:
    """Create a new calendar event.

    Only call this after reading the event back to the user - title, start
    and end time, and calendar - and getting their explicit confirmation,
    in this same turn. This tool creates the event immediately with no
    built-in pause of its own.

    Args:
        title: Event title.
        start_datetime: Start time, as 'YYYY-MM-DD HH:MM'.
        end_datetime: End time, as 'YYYY-MM-DD HH:MM'.
        calendar_name: Which calendar to add it to. Leave empty to use the
            default calendar. Use an iCloud calendar (not "On My Mac") if
            the event should also show up on the user's iPhone.
        location: Optional event location.
    """
    try:
        start_dt = _parse_datetime(start_datetime)
        end_dt = _parse_datetime(end_datetime)

        # Calendar.app has no "default calendar" term - fall back to the
        # first writable calendar (many accounts include read-only ones
        # like Holidays or Birthdays, which can't take new events).
        target_calendar = (
            f'calendar "{_escape_as(calendar_name)}"'
            if calendar_name else "item 1 of (calendars whose writable is true)"
        )

        script = f'''
        {_applescript_date_block("evtStart", start_dt)}
        {_applescript_date_block("evtEnd", end_dt)}
        tell application "Calendar"
            tell {target_calendar}
                set newEvent to make new event with properties {{summary:"{_escape_as(title)}", start date:evtStart, end date:evtEnd, location:"{_escape_as(location)}"}}
            end tell
        end tell
        return "ok"
        '''

        _run_osascript(script)

        return f"Created event '{title}' from {start_datetime} to {end_datetime}."

    except Exception as e:
        return f"Couldn't create the event: {e}"


@function_tool
def list_reminders(list_name: str = "", include_completed: bool = False) -> str:
    """List reminders.

    Args:
        list_name: Only look in this specific reminders list. Leave empty
            to search every list.
        include_completed: Whether to include reminders already marked done.
    """
    try:
        list_filter = (
            f'lists whose name is "{_escape_as(list_name)}"' if list_name else "lists"
        )
        completed_filter = "" if include_completed else " whose completed is false"

        script = f'''
        set output to ""
        tell application "Reminders"
            repeat with lst in ({list_filter})
                repeat with r in (every reminder of lst{completed_filter})
                    set dueText to ""
                    try
                        set dueText to (due date of r) as string
                    end try
                    set output to output & (name of r) & "|" & dueText & "|" & (completed of r) & "|" & (name of lst) & "\\n"
                end repeat
            end repeat
        end tell
        return output
        '''

        raw = _run_osascript(script)
        lines = [line for line in raw.splitlines() if line.strip()]

        if not lines:
            return "No reminders found."

        formatted = []
        for line in lines:
            parts = line.split("|", 3)
            if len(parts) != 4:
                continue
            name, due, completed, lst = parts
            status = "done" if completed == "true" else "open"
            due_part = f", due {due}" if due else ""
            formatted.append(f"- {name} ({lst}, {status}{due_part})")

        return "\n".join(formatted)

    except Exception as e:
        return f"Couldn't get reminders: {e}"


@function_tool
def create_reminder(title: str, due_date: str = "", list_name: str = "") -> str:
    """Create a new reminder.

    Only call this after reading the reminder back to the user - title,
    due date if any, and list - and getting their explicit confirmation,
    in this same turn. This tool creates the reminder immediately with no
    built-in pause of its own.

    Args:
        title: Reminder text.
        due_date: Optional due date/time, as 'YYYY-MM-DD HH:MM' or
            'YYYY-MM-DD'. Leave empty for no due date.
        list_name: Which reminders list to add it to. Leave empty to use
            the default list. Use an iCloud list (not "On My Mac") if the
            reminder should also show up on the user's iPhone.
    """
    try:
        target_list = (
            f'list "{_escape_as(list_name)}"' if list_name else "default list"
        )

        due_block = ""
        due_prop = ""
        if due_date:
            due_dt = _parse_datetime(due_date)
            due_block = _applescript_date_block("dueDate", due_dt)
            due_prop = ", due date:dueDate"

        script = f'''
        {due_block}
        tell application "Reminders"
            tell {target_list}
                set newReminder to make new reminder with properties {{name:"{_escape_as(title)}"{due_prop}}}
            end tell
        end tell
        return "ok"
        '''

        _run_osascript(script)

        due_note = f" due {due_date}" if due_date else ""
        return f"Created reminder '{title}'{due_note}."

    except Exception as e:
        return f"Couldn't create the reminder: {e}"


@function_tool
def complete_reminder(title: str, list_name: str = "") -> str:
    """Mark a reminder as completed.

    Args:
        title: The reminder's name (or a close match) - the first matching,
            not-yet-completed reminder found is marked done.
        list_name: Which reminders list to search. Leave empty to search
            every list.
    """
    try:
        list_filter = (
            f'lists whose name is "{_escape_as(list_name)}"' if list_name else "lists"
        )

        script = f'''
        tell application "Reminders"
            repeat with lst in ({list_filter})
                repeat with r in (every reminder of lst whose completed is false)
                    if (name of r) contains "{_escape_as(title)}" then
                        set completed of r to true
                        return (name of r)
                    end if
                end repeat
            end repeat
        end tell
        return ""
        '''

        result = _run_osascript(script)

        if not result:
            return f"No open reminder matching '{title}' was found."

        return f"Marked '{result}' as completed."

    except Exception as e:
        return f"Couldn't complete the reminder: {e}"