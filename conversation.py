"""
Shared conversation state.

Both voice and text input funnel through the same Conversation object, so:
- history carries across turns (it's a real back-and-forth, not one-shot)
- switching between talking and typing mid-conversation keeps context
"""

from agents import Runner

from agents_setup import triage_agent


class Conversation:
    def __init__(self):
        self.history = []

    async def send(self, user_text: str) -> str:
        """Send a message, get the reply, and remember this turn for next time."""
        self.history.append({"role": "user", "content": user_text})
        result = await Runner.run(triage_agent, self.history)
        self.history = result.to_input_list()

        reply = (result.final_output or "").strip()
        if not reply:
            print(f"[debug] empty final_output. last_agent={getattr(result, 'last_agent', None)}")
            reply = "Sorry, I didn't get a clear response for that - could you try again?"
        return reply

    def reset(self):
        """Start a fresh conversation with no memory of prior turns."""
        self.history = []