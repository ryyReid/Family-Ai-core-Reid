"""
MasterOrchestrator — family's central brain.
Watches all agents, spots conflicts, sends nudges.
"""

from __future__ import annotations
import json
import re
from core import db, llm

MASTER_SYSTEM = """You are the Master Orchestrator of a Family AI system.
You oversee personal AI agents — one per family member.
You CANNOT talk directly to family members. You communicate by sending
nudges to their agents, who deliver the message naturally.

Family members and agents: {agents}

REAL family activity (FAEs — these are facts, not examples):
{faes}

Recent agent reports:
{messages}

Memories:
{memories}

When sending a nudge output ONLY this exact JSON on its own line:
{{"nudge": true, "to_agent": "agent_namehere", "message": "friendly natural message"}}

Rules:
- Only reference events that actually appear in the FAEs above. NEVER invent events.
- Keep nudge messages friendly and natural — the agent will slip it into conversation.
- Never expose system internals in nudge text.
- If there is nothing useful to coordinate, say so clearly.
"""


class MasterOrchestrator:
    def __init__(self, agents: dict[str, object]):
        self.agents   = agents
        self.agent_id = "master"

    def chat(self, user_input: str) -> str:
        system  = self._build_system()
        history = db.get_conversation(self.agent_id, limit=12)
        history.append({"role": "user", "content": user_input})
        reply   = llm.chat(history, system=system, temperature=0.65, max_tokens=400)
        db.add_conversation_turn(self.agent_id, "user", user_input)
        db.add_conversation_turn(self.agent_id, "assistant", reply)
        self._parse_and_dispatch(reply)
        return reply

    def reflect(self) -> list[str]:
        """Scan REAL FAEs only and nudge where coordination is genuinely needed."""
        faes = db.get_faes(limit=20)
        if not faes:
            return []

        fae_text = "\n".join(
            f"  [{f['timestamp'][:16]}] {f['member']} {f['action']} {f['activity']}"
            for f in faes
        )
        members = list(self.agents.keys())

        prompt = (
            f"Family members: {', '.join(members)}\n\n"
            f"Here are the ONLY real events logged so far:\n{fae_text}\n\n"
            "Based ONLY on these real events:\n"
            "- Are there any scheduling conflicts?\n"
            "- Is there info one member shared that another should know?\n"
            "- Any coordination that would genuinely help?\n\n"
            "If yes, send a nudge using the JSON format. "
            "If nothing useful to coordinate, just say 'No coordination needed.'\n"
            "Do NOT invent events. Only work with what is listed above."
        )

        system  = self._build_system()
        reply   = llm.chat([{"role": "user", "content": prompt}],
                           system=system, temperature=0.4, max_tokens=400)
        dispatched = self._parse_and_dispatch(reply)
        db.save_memory(self.agent_id, f"Reflection: {reply[:200]}", "reflection")
        return dispatched, reply

    def nudge(self, target_member: str, message: str, priority: str = "normal") -> str:
        agent_name = f"agent_{target_member.lower()}"
        msg_type   = "alert" if priority == "alert" else "nudge"
        return db.send_message(
            from_agent=self.agent_id, to_agent=agent_name,
            msg_type=msg_type, payload={"message": message, "from": "master"},
        )

    def relay(self, from_member: str, to_member: str, message: str) -> str:
        # Use a plain system prompt — no JSON nudge format, just plain text output
        simple_system = (
            "You are a helpful family coordinator. Write one short, friendly, "
            "natural-sounding sentence to pass along information from one family "
            "member to another. Plain text only — no JSON, no quotes, no formatting."
        )
        prompt = (
            f"{from_member} shared this: \"{message}\"\n"
            f"Write one sentence to naturally tell {to_member} about this."
        )
        nudge_text = llm.chat(
            [{"role": "user", "content": prompt}],
            system=simple_system, max_tokens=80, temperature=0.7,
        )
        # Strip any accidental JSON or backticks the model might add
        import re as _re
        nudge_text = _re.sub(r"```.*?```", "", nudge_text, flags=_re.DOTALL).strip()
        nudge_text = _re.sub(r'\{.*?\}', "", nudge_text, flags=_re.DOTALL).strip()
        nudge_text = nudge_text.strip('"\'` \n')
        self.nudge(to_member, nudge_text)
        db.add_fae("Master", "relayed",
                   f"{from_member} → {to_member}: {message[:60]}", source="master_relay")
        return nudge_text

    def process_agent_reports(self) -> int:
        msgs = db.get_pending_messages("master")
        for msg in msgs:
            db.mark_message_delivered(msg["id"])
        return len(msgs)

    def status(self) -> dict:
        return {
            "members":        [m["name"] for m in db.get_members()],
            "recent_faes":    len(db.get_faes(limit=20)),
            "pending_chores": len(db.get_chores()),
            "grocery_items":  len(db.get_grocery()),
            "bus_messages":   len(db.get_message_history(limit=20)),
            "memories":       len(db.get_all_memories(limit=10)),
        }

    def _build_system(self) -> str:
        agent_list = ", ".join(
            f"{name} → agent_{name.lower()}" for name in self.agents
        )
        faes = db.get_faes(limit=15)
        fae_lines = "\n".join(
            f"  [{f['timestamp'][:16]}] {f['member']} {f['action']} {f['activity']}"
            for f in faes
        ) or "  (no events logged yet)"

        msgs = db.get_message_history(limit=10)
        msg_lines = "\n".join(
            f"  {m['from_agent']} → {m['to_agent']} [{m['msg_type']}]: "
            f"{json.loads(m['payload']).get('summary', json.loads(m['payload']).get('message',''))[:80]}"
            for m in msgs
        ) or "  (none)"

        memories  = db.get_all_memories(limit=8)
        mem_lines = "\n".join(f"  • {m['content']}" for m in memories) or "  (none)"

        return MASTER_SYSTEM.format(
            agents=agent_list, faes=fae_lines,
            messages=msg_lines, memories=mem_lines,
        )

    def _parse_and_dispatch(self, reply: str) -> list[str]:
        dispatched = []
        for match in re.finditer(r'\{[^{}]*"nudge"\s*:\s*true[^{}]*\}', reply, re.DOTALL):
            try:
                data = json.loads(match.group())
                if data.get("nudge") and data.get("to_agent") and data.get("message"):
                    db.send_message(
                        from_agent=self.agent_id, to_agent=data["to_agent"],
                        msg_type="nudge", payload={"message": data["message"]},
                    )
                    dispatched.append(f"{data['to_agent']}: {data['message'][:70]}")
            except json.JSONDecodeError:
                pass
        return dispatched