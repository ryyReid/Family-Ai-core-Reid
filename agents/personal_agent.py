"""
PersonalAgent — one instance per family member.
No circular imports. No self-referencing imports.
"""

import json
from core import db, llm

AGENT_SYSTEM = """You are {name}'s personal Family AI assistant — friendly, warm, and concise.
Feel like texting a helpful friend, not reading a dashboard.
Keep replies SHORT (1-3 sentences) unless they ask for detail.

Family members: {members}
{name}'s preferences: {preferences}
{name}'s dietary needs: {dietary}

Recent family activity (for context only — do NOT repeat these unprompted):
{fae_context}

Things you remember about {name}:
{memories}

{nudge_section}

STRICT RULES — never break these:
1. Never say the words "nudge", "NUDGE", "I was told", "I received", "system", or anything revealing internal mechanics.
2. Background info and nudges are ONE-TIME — mention each piece of info AT MOST ONCE per conversation, then drop it.
3. Only bring up family context if {name} directly asks, or it is immediately relevant to what they just said.
4. Do NOT volunteer reminders, past events, or family updates repeatedly. Say it once, move on.
5. Keep replies SHORT. 1-2 sentences. You are a helpful friend, not a news ticker.
"""

NUDGE_SECTION = """Background context to work in naturally when the moment is right:
{nudges}"""


class PersonalAgent:
    def __init__(self, member_name):
        self.name      = member_name
        self.agent_id  = "agent_" + member_name.lower()
        self._pending_nudges = []

    def chat(self, user_input):
        self._collect_nudges()
        system  = self._build_system()
        history = db.get_conversation(self.agent_id, limit=16)
        history.append({"role": "user", "content": user_input})
        reply   = llm.chat(history, system=system, temperature=0.72, max_tokens=300)
        db.add_conversation_turn(self.agent_id, "user", user_input)
        db.add_conversation_turn(self.agent_id, "assistant", reply)
        self._extract_fae(user_input)
        db.send_message(
            from_agent = self.agent_id,
            to_agent   = "master",
            msg_type   = "fae",
            payload    = {
                "member":  self.name,
                "input":   user_input,
                "summary": reply[:120],
            },
        )
        self._pending_nudges.clear()
        return reply

    def _collect_nudges(self):
        for msg in db.get_pending_messages(self.agent_id):
            payload = json.loads(msg["payload"])
            text    = payload.get("message", "").strip()
            if text:
                if msg["msg_type"] == "alert":
                    self._pending_nudges.insert(0, text)
                else:
                    self._pending_nudges.append(text)
            db.mark_message_delivered(msg["id"])

    def _extract_fae(self, text):
        t = text.lower()
        action_map = [
            ("going to",      "planned"),
            ("planning to",   "planned"),
            ("i'll",          "planned"),
            ("i will",        "planned"),
            ("want to",       "expressed_interest"),
            ("would like",    "expressed_interest"),
            ("interested in", "expressed_interest"),
            ("need",          "needs"),
            ("remind me",     "requested_reminder"),
            ("done",          "completed"),
            ("finished",      "completed"),
            ("bought",        "purchased"),
            ("love",          "prefers"),
            ("like",          "prefers"),
            ("hate",          "dislikes"),
            ("allergic",      "dietary_restriction"),
        ]
        for keyword, action in action_map:
            if keyword in t:
                db.add_fae(
                    member   = self.name,
                    action   = action,
                    activity = text.strip().rstrip(".")[:100],
                    detail   = text,
                    source   = "chat_" + self.agent_id,
                )
                break

    def _build_system(self):
        members      = db.get_members()
        member_names = ", ".join(m["name"] for m in members) or "the family"
        member_data  = db.get_member(self.name) or {}
        prefs_raw    = member_data.get("preferences", "{}")
        dietary_raw  = member_data.get("dietary", "[]")
        # Parse into readable text for the LLM
        import json as _json
        try:
            prefs_dict = _json.loads(prefs_raw) if isinstance(prefs_raw, str) else prefs_raw
            prefs = prefs_dict.get("notes", str(prefs_dict)) if isinstance(prefs_dict, dict) else str(prefs_dict)
        except Exception:
            prefs = str(prefs_raw)
        try:
            dietary_list = _json.loads(dietary_raw) if isinstance(dietary_raw, str) else dietary_raw
            dietary = ", ".join(dietary_list) if dietary_list else "none"
        except Exception:
            dietary = str(dietary_raw)
        faes         = db.get_faes(limit=14)
        fae_lines    = "\n".join(
            "  * " + f["member"] + " " + f["action"] + " " + f["activity"]
            for f in faes
        ) or "  (none yet)"
        memories     = db.get_memories(self.agent_id, limit=6)
        mem_lines    = "\n".join("  * " + m["content"] for m in memories) or "  (none yet)"
        if self._pending_nudges:
            nudge_text    = "\n".join("  - " + n for n in self._pending_nudges)
            nudge_section = NUDGE_SECTION.format(nudges=nudge_text)
        else:
            nudge_section = ""
        return AGENT_SYSTEM.format(
            name          = self.name,
            members       = member_names,
            preferences   = prefs,
            dietary       = dietary,
            fae_context   = fae_lines,
            memories      = mem_lines,
            nudge_section = nudge_section,
        )

    def save_memory(self, content, memory_type="observation"):
        db.save_memory(self.agent_id, content, memory_type, related_to=self.name)

    def __repr__(self):
        return "<PersonalAgent:" + self.name + ">"