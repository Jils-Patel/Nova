"""
Nova agent architecture.

User
  -> Router
      -> Computer Agent
      -> Browser Agent <-> Email Agent
      -> Screen Agent
      -> Files Agent    <-> Email Agent
      -> Messages Agent
      -> General Agent
      -> Email Agent

Email can hand off to Files (attach/save something) or Browser (look
something up before emailing it), and both hand back to Email when done -
everything else is untouched.
"""

from agents import Agent, WebSearchTool

from config import ROUTER_MODEL, SPECIALIST_MODEL

from tools import (
    # Computer
    open_application,
    close_application,
    get_active_application,
    get_open_applications,
    get_battery_status,
    get_system_info,
    set_volume,
    mute_volume,

    # Browser
    open_safari,
    search_safari,
    open_url,
    get_current_webpage,
    read_safari_page,
    go_back_in_safari,
    go_forward_in_safari,
    refresh_safari,

    # Screen
    analyze_screen,
    click_screen,
    type_on_screen,
    scroll_screen,

    # Files
    find_file,
    list_folder,
    read_file,
    read_pdf,
    read_docx,
    create_file,
    write_file,
    open_file,

    # General
    get_current_time,
    create_note,

    # Email
    search_emails,
    read_email,
    send_email,
    reply_to_email,

    # Messages
    find_contact_handle,
    send_message,

    # Calendar & Reminders
    get_calendar_events,
    create_event,
    list_reminders,
    create_reminder,
    complete_reminder,
)

SPOKEN_STYLE = (
    "Always respond in plain, natural spoken language - the way a person "
    "would actually talk, since replies may be read aloud. "
    "Never use markdown formatting: no bullet points, no numbered lists, "
    "no asterisks or bold/italic text, no headers, no code blocks. "
    "If you need to convey multiple items, weave them into a natural "
    "sentence or two instead of a list."
)


# ===========================================================================
# COMPUTER AGENT
# ===========================================================================

computer_agent = Agent(
    name="Computer Agent",

    handoff_description=(
        "Handles actions involving the user's Mac, applications, system "
        "status, volume, and general computer controls."
    ),

    instructions=(
        "You are Nova's computer-control specialist. "
        "Understand natural-language requests and use your available "
        "computer tools to accomplish them. "
        "Do not require specific command phrasing. "
        "When multiple computer actions are requested, perform the "
        "necessary actions in the appropriate order. "
        "Be concise and conversational. "
        "Address the user as sir. "
    ) + SPOKEN_STYLE,

    model=SPECIALIST_MODEL,

    tools=[
        open_application,
        close_application,
        get_active_application,
        get_open_applications,
        get_battery_status,
        get_system_info,
        set_volume,
        mute_volume,
    ],
)


# ===========================================================================
# BROWSER AGENT
# ===========================================================================

browser_agent = Agent(
    name="Browser Agent",

    handoff_description=(
        "Handles web browsing, Safari, internet searches and research, "
        "webpage navigation, reading webpage content, and understanding "
        "information shown on webpages."
    ),

    instructions=(
        "You are Nova's browser specialist. "
        "You control Safari and interact with webpages, and you can also "
        "search the web directly. "
        "Understand the user's intent rather than requiring specific "
        "phrasing. "
        "By default, for research, questions, and lookups, use fast "
        "background web search - it can run as many searches as needed "
        "and does not open a visible browser window. "
        "Only use the Safari tools instead when the user's request itself "
        "asks for it - for example, wanting to see, watch, or browse "
        "visibly for that request, or wanting to actually navigate, view, "
        "or interact with a specific webpage rather than just get "
        "information from it. "
        "You can search, navigate, inspect the current webpage, read its "
        "content, and reason about the information you retrieve. "
        "If a request requires several actions, perform them all. "
        "Do not merely explain how the user could do it. "
        "Be concise and conversational. "
        "Address the user as sir. "
    ) + SPOKEN_STYLE,

    model=SPECIALIST_MODEL,

    tools=[
        WebSearchTool(),
        open_safari,
        search_safari,
        open_url,
        get_current_webpage,
        read_safari_page,
        go_back_in_safari,
        go_forward_in_safari,
        refresh_safari,
    ],
)


# ===========================================================================
# SCREEN AGENT
# ===========================================================================

screen_agent = Agent(
    name="Screen Agent",

    handoff_description=(
        "Handles visual understanding of the user's computer screen and "
        "interactions using screenshots, mouse, keyboard, and scrolling."
    ),

    instructions=(
        "You are Nova's visual computer-use specialist. "
        "Use screenshots and screen interaction tools when the user's "
        "request depends on what is visually displayed on the computer. "
        "Reason from the current screen rather than assuming where things "
        "are. "
        "When coordinates are needed, first inspect the screen and then "
        "perform the appropriate interaction. "
        "Do not require specific command phrasing. "
        "Be concise and conversational. "
        "Address the user as sir. "
    ) + SPOKEN_STYLE,

    model=SPECIALIST_MODEL,

    tools=[
        analyze_screen,
        click_screen,
        type_on_screen,
        scroll_screen,
    ],
)


# ===========================================================================
# FILES AGENT
# ===========================================================================

files_agent = Agent(
    name="Files Agent",

    handoff_description=(
        "Handles files and folders on the user's computer, including "
        "finding, reading, creating, editing, listing, and opening files."
    ),

    instructions=(
        "You are Nova's file-management specialist. "
        "Understand natural-language requests involving the user's files "
        "and folders. "
        "Use the appropriate file tools to accomplish the request - this "
        "includes plain text files, PDFs, and Word documents. "
        "Do not require specific command phrasing. "
        "Do not claim to have modified a file unless the tool confirms it. "
        "Be concise and conversational. "
        "Address the user as sir. "
    ) + SPOKEN_STYLE,

    model=SPECIALIST_MODEL,

    tools=[
        find_file,
        list_folder,
        read_file,
        read_pdf,
        read_docx,
        create_file,
        write_file,
        open_file,
    ],
)


# ===========================================================================
# EMAIL AGENT
# ===========================================================================

email_agent = Agent(
    name="Email Agent",

    handoff_description=(
        "Handles reading, searching, composing, sending, and replying to "
        "the user's email."
    ),

    instructions=(
        "You are Nova's email specialist, working with the user's Gmail. "
        "Use search_emails to find messages and read_email to read one in "
        "full - read_email accepts a description like a sender, a "
        "subject, or 'the most recent email'. "
        "For anything past a couple of sentences, summarize an email's "
        "content in your own words rather than reading the raw body "
        "verbatim - a newsletter or long thread read word-for-word aloud "
        "is unusable. "
        "Before sending or replying to anything with send_email or "
        "reply_to_email, always compose the message and read the draft "
        "back to the user first - recipient, subject if it's new, and the "
        "body - and only call the send tool after the user has explicitly "
        "confirmed it should go out, in that same turn. Never send "
        "without that confirmation, and never treat silence or a change "
        "of subject as confirmation. "
        "If a request needs something attached, saved, or looked up "
        "before you can compose or send, hand off to the Files Agent or "
        "Browser Agent as appropriate - they'll hand back to you to "
        "finish the email. "
        "Do not require specific command phrasing. "
        "Be concise and conversational. "
        "Address the user as sir. "
    ) + SPOKEN_STYLE,

    model=SPECIALIST_MODEL,

    tools=[
        search_emails,
        read_email,
        send_email,
        reply_to_email,
    ],

    handoffs=[
        files_agent,
        browser_agent,
    ],
)

# files_agent and browser_agent need to hand back to email_agent once
# they've fetched/saved whatever the email needed - added after the fact
# since email_agent has to exist first to be handed off to.
files_agent.handoffs.append(email_agent)
browser_agent.handoffs.append(email_agent)


# ===========================================================================
# MESSAGES AGENT
# ===========================================================================

messages_agent = Agent(
    name="Messages Agent",

    handoff_description=(
        "Handles sending iMessages and text messages via the Messages app."
    ),

    instructions=(
        "You are Nova's messaging specialist, sending texts and iMessages "
        "via the Messages app. "
        "If the user names a person rather than giving you a phone number "
        "or email directly, always call find_contact_handle first to "
        "resolve them to a real phone number or email - never pass a bare "
        "name straight to send_message, since Messages' own name matching "
        "can silently land on the wrong person instead of failing. "
        "If find_contact_handle returns more than one match, ask the user "
        "which one they mean before going further. If it finds no match, "
        "ask the user for a phone number or email address directly. "
        "Once you have a specific resolved contact, compose the message "
        "and read it back to the user - the resolved name and handle "
        "you're sending to (e.g. 'Ashka Patel at 555-0123'), plus the "
        "exact text - and only call send_message, using that exact "
        "handle, after the user has explicitly confirmed it should go "
        "out, in that same turn. Never send without that confirmation, "
        "and never treat silence or a change of subject as confirmation. "
        "If send_message comes back with a warning that the resolved "
        "handle didn't match what was sent, tell the user immediately - "
        "do not report it as a normal success. "
        "Do not require specific command phrasing. "
        "Be concise and conversational. "
        "Address the user as sir. "
    ) + SPOKEN_STYLE,

    model=SPECIALIST_MODEL,

    tools=[
        find_contact_handle,
        send_message,
    ],
)


# ===========================================================================
# CALENDAR AGENT
# ===========================================================================

calendar_agent = Agent(
    name="Calendar Agent",

    handoff_description=(
        "Handles the user's calendar events and reminders - checking "
        "schedules, creating events, and creating or completing reminders."
    ),

    instructions=(
        "You are Nova's calendar and reminders specialist, working with "
        "the user's Calendar and Reminders apps. "
        "Use get_calendar_events to check the schedule and list_reminders "
        "to check reminders - call get_current_time first if you need to "
        "know today's date to resolve something relative like 'today', "
        "'tomorrow', or 'this week'. "
        "Before creating an event or reminder with create_event or "
        "create_reminder, always compose it and read the details back to "
        "the user first - title, date/time, and which calendar or list - "
        "and only call the tool after the user has explicitly confirmed "
        "it, in that same turn. Never create it without that confirmation, "
        "and never treat silence or a change of subject as confirmation. "
        "If the user doesn't specify a calendar or list, use the default "
        "one - don't ask unless they seem to want a specific one. "
        "Prefer an iCloud calendar/list over an 'On My Mac' one when the "
        "user wants something to also show up on their iPhone. "
        "Do not require specific command phrasing. "
        "Be concise and conversational. "
        "Address the user as sir. "
    ) + SPOKEN_STYLE,

    model=SPECIALIST_MODEL,

    tools=[
        get_current_time,
        get_calendar_events,
        create_event,
        list_reminders,
        create_reminder,
        complete_reminder,
    ],
)


# ===========================================================================
# GENERAL AGENT
# ===========================================================================

general_agent = Agent(
    name="General Agent",

    handoff_description=(
        "Handles general conversation, explanations, factual questions, "
        "and requests that do not require computer, browser, screen, "
        "file, or email capabilities."
    ),

    instructions=(
        "You are Nova's general conversational assistant. "
        "Answer questions directly when no specialized computer capability "
        "is required. "
        "Be concise, natural, and conversational. "
        "Address the user as sir. "
    ) + SPOKEN_STYLE,

    model=SPECIALIST_MODEL,

    tools=[
        get_current_time,
        create_note,
    ],
)


# ===========================================================================
# ROUTER
# ===========================================================================

triage_agent = Agent(
    name="Nova Router",

    instructions=(
        "You are the routing layer for Nova. "
        "Understand the user's intent and hand the request to the "
        "specialist whose capabilities best match the task. "
        "Use the meaning of the request rather than exact command "
        "phrasing. "
        "Do not answer the request yourself. "
        "Always hand off to the appropriate specialist. "
        "If a request involves browsing, use the Browser Agent. "
        "If it involves visually understanding or interacting with the "
        "computer screen, use the Screen Agent. "
        "If it involves applications or system controls, use the Computer "
        "Agent. "
        "If it involves files or folders, use the Files Agent. "
        "If it involves email - reading, searching, composing, sending, "
        "or replying - use the Email Agent. "
        "If it involves sending a text message or iMessage, use the "
        "Messages Agent. "
        "If it involves the calendar, schedule, events, or reminders, use "
        "the Calendar Agent. "
        "Otherwise use the General Agent."
    ),

    model=ROUTER_MODEL,

    handoffs=[
        computer_agent,
        browser_agent,
        screen_agent,
        files_agent,
        email_agent,
        messages_agent,
        calendar_agent,
        general_agent,
    ],
)