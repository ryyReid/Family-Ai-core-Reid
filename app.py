"""
Family Fabric — Chainlit GUI
Run with: chainlit run app.py

Each family member logs in with their name + password.
Master logs in as "master" to access the admin console.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import chainlit as cl
from core import db, llm

# ── Family member passwords — edit these ─────────────────────────────────────
# name must match exactly what was entered during --setup (case-insensitive)
FAMILY_PASSWORDS = {
    "mom":    "mom123",
    "dad":    "dad123",
    "feed":   "feed123",
    "logan":  "logan123",
    "earl":   "earl123",
    "master": "master999",
}

db.init_db()


# ══════════════════════════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════════════════════════

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    key = username.strip().lower()
    if key in FAMILY_PASSWORDS and FAMILY_PASSWORDS[key] == password:
        members  = db.get_members()
        real_name = next(
            (m["name"] for m in members if m["name"].lower() == key),
            username.strip()
        )
        role = "master" if key == "master" else "member"
        return cl.User(identifier=real_name, metadata={"role": role})
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  CHAT START
# ══════════════════════════════════════════════════════════════════════════════

@cl.on_chat_start
async def on_chat_start():
    from agents.personal_agent import PersonalAgent
    from agents.master import MasterOrchestrator

    user = cl.user_session.get("user")
    name = user.identifier
    role = user.metadata.get("role", "member")

    members = db.get_members()
    agents  = {m["name"]: PersonalAgent(m["name"]) for m in members}
    master  = MasterOrchestrator(agents)

    cl.user_session.set("master", master)
    cl.user_session.set("role", role)
    cl.user_session.set("name", name)

    if role == "master":
        cl.user_session.set("role", "master")
        await cl.Message(content=(
            f"👋 **Master Console**\n\n"
            f"Family: {', '.join(agents.keys())}\n\n"
            f"**Commands:**\n"
            f"- `nudge <name> <message>`\n"
            f"- `relay <From> <To> <message>`\n"
            f"- `reflect`\n"
            f"- `faes` / `faes <name>`\n"
            f"- `status` / `chores` / `grocery`\n"
            f"- Or just ask anything about the family."
        )).send()
        return

    # Member — set up personal agent
    agent = agents[name]
    cl.user_session.set("agent", agent)

    # Deliver any pending nudges as opening greeting
    pending = db.get_pending_messages(f"agent_{name.lower()}")
    if pending:
        import json
        nudge_texts = []
        for msg in pending:
            payload = json.loads(msg["payload"])
            text    = payload.get("message", "").strip()
            if text:
                nudge_texts.append(text)
            db.mark_message_delivered(msg["id"])
        agent._pending_nudges.clear()

        if nudge_texts:
            nudge_summary = " | ".join(nudge_texts)
            try:
                greeting = agent.chat(
                    f"[one-time delivery] Greet {name} and mention this naturally "
                    f"in 1-2 sentences (never repeat it): {nudge_summary}"
                )
                await cl.Message(content=greeting).send()
                return
            except Exception:
                pass

    # Plain greeting (no nudges)
    try:
        greeting = agent.chat(f"[session start] Give {name} a very short friendly hello.")
        await cl.Message(content=greeting).send()
    except ConnectionError:
        await cl.Message(content=f"Hey {name}! 👋 (LM Studio not connected yet)").send()


# ══════════════════════════════════════════════════════════════════════════════
#  MESSAGE HANDLER
# ══════════════════════════════════════════════════════════════════════════════

@cl.on_message
async def on_message(message: cl.Message):
    role = cl.user_session.get("role")
    if role == "master":
        await _master_handler(message.content.strip())
    else:
        await _member_handler(message.content.strip())


async def _member_handler(text: str):
    agent  = cl.user_session.get("agent")
    master = cl.user_session.get("master")
    try:
        async with cl.Step(name="thinking") as step:
            step.output = "..."
        reply = agent.chat(text)
        master.process_agent_reports()
        await cl.Message(content=reply).send()
    except ConnectionError:
        await cl.Message(content="⚠️ LM Studio not reachable. Start it and load a model.").send()
    except Exception as e:
        await cl.Message(content=f"⚠️ {e}").send()


async def _master_handler(text: str):
    master       = cl.user_session.get("master")
    members      = db.get_members()
    member_names = [m["name"] for m in members]

    parts = text.split(None, 1)
    cmd   = parts[0].lower()
    rest  = parts[1] if len(parts) > 1 else ""

    if cmd == "status":
        s = master.status()
        await cl.Message(content=(
            f"**📊 Family Status**\n"
            f"- Members: {', '.join(s['members'])}\n"
            f"- Recent FAEs: {s['recent_faes']}\n"
            f"- Pending chores: {s['pending_chores']}\n"
            f"- Grocery items: {s['grocery_items']}\n"
            f"- Bus messages: {s['bus_messages']}"
        )).send()

    elif cmd == "faes":
        member_filter = rest.strip() or None
        faes = db.get_faes(member=member_filter, limit=20)
        if not faes:
            await cl.Message(content="No FAEs logged yet.").send()
            return
        header = f"**📋 FAEs**" + (f" — {member_filter}" if member_filter else "")
        lines  = [header]
        for f in faes:
            lines.append(f"`{f['timestamp'][:16]}` **{f['member']}** {f['action']} — {f['activity']}")
        await cl.Message(content="\n".join(lines)).send()

    elif cmd == "nudge":
        p = rest.split(None, 1)
        if len(p) < 2:
            await cl.Message(content="Usage: `nudge <name> <message>`").send()
            return
        target, msg = p[0], p[1]
        match = next((n for n in member_names if n.lower() == target.lower()), None)
        if not match:
            await cl.Message(content=f"Unknown member: {target}").send()
            return
        master.nudge(match, msg)
        await cl.Message(content=f"✅ Nudge queued for **{match}**. They'll hear it next time they chat.").send()

    elif cmd == "relay":
        p = rest.split(None, 2)
        if len(p) < 3:
            await cl.Message(content="Usage: `relay <From> <To> <message>`").send()
            return
        frm, to_, msg = p
        fm = next((n for n in member_names if n.lower() == frm.lower()), None)
        tm = next((n for n in member_names if n.lower() == to_.lower()), None)
        if not fm or not tm:
            await cl.Message(content=f"Unknown member. Known: {member_names}").send()
            return
        try:
            async with cl.Step(name="framing relay") as step:
                step.output = f"{fm} → {tm}"
            nudge_text = master.relay(fm, tm, msg)
            await cl.Message(content=f"✅ Relayed. **{tm}**'s agent will say:\n> {nudge_text}").send()
        except ConnectionError:
            await cl.Message(content="⚠️ LM Studio not reachable.").send()

    elif cmd == "reflect":
        try:
            async with cl.Step(name="scanning family activity") as step:
                step.output = "Reading FAEs..."
            result = master.reflect()
            dispatched, analysis = result if isinstance(result, tuple) else (result, "")
            lines = [f"**🔍 Reflection**\n{analysis[:500]}"]
            if dispatched:
                lines.append("\n**Nudges dispatched:**")
                for d in dispatched:
                    lines.append(f"→ {d}")
            else:
                lines.append("\n_No coordination needed._")
            await cl.Message(content="\n".join(lines)).send()
        except ConnectionError:
            await cl.Message(content="⚠️ LM Studio not reachable.").send()

    elif cmd == "chores":
        chores = db.get_chores()
        if not chores:
            await cl.Message(content="No pending chores.").send()
            return
        lines = ["**🧹 Pending Chores**"]
        for c in chores:
            lines.append(f"- **{c['member']}**: {c['task']} ({c['frequency']})")
        await cl.Message(content="\n".join(lines)).send()

    elif cmd == "grocery":
        items = db.get_grocery()
        if not items:
            await cl.Message(content="Grocery list is empty.").send()
            return
        lines = ["**🛒 Grocery List**"]
        last_cat = None
        for item in items:
            if item["category"] != last_cat:
                lines.append(f"\n_{item['category']}_")
                last_cat = item["category"]
            lines.append(f"- {item['item']} ({item['qty']})")
        await cl.Message(content="\n".join(lines)).send()

    else:
        try:
            async with cl.Step(name="thinking") as step:
                step.output = "..."
            reply = master.chat(text.strip("`").strip())
            await cl.Message(content=reply).send()
        except ConnectionError:
            await cl.Message(content="⚠️ LM Studio not reachable.").send()
        except Exception as e:
            await cl.Message(content=f"⚠️ {e}").send()
