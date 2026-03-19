#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════╗
║           FAMILY FABRIC  —  CLI                      ║
║   Master + Personal Agents, all in your terminal     ║
╚══════════════════════════════════════════════════════╝

Usage:
  python main.py                        # interactive menu
  python main.py --member Mom           # drop straight into Mom's chat
  python main.py --master               # drop straight into master console
  python main.py --setup                # first-run family setup
"""

import sys
import os
# Make sure Python can find core/ and agents/ regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import argparse
import json
from core import db, llm
# agents imported inside functions to avoid circular import at module load

# ── ANSI colors (degrade gracefully on Windows) ─────────────────────────────
try:
    import os; os.get_terminal_size()
    R  = "\033[91m"   # red
    G  = "\033[92m"   # green
    Y  = "\033[93m"   # yellow
    B  = "\033[94m"   # blue
    M  = "\033[95m"   # magenta
    C  = "\033[96m"   # cyan
    W  = "\033[97m"   # white
    DIM= "\033[2m"
    RST= "\033[0m"
except Exception:
    R=G=Y=B=M=C=W=DIM=RST=""

BANNER = f"""
{C}╔══════════════════════════════════════════════════════╗
║  {W}🏠  Family Fabric  {DIM}— AI-first family coordination{RST}{C}   ║
║  {DIM}Local LLM · Personal Agents · Master Orchestrator{RST}{C}  ║
╚══════════════════════════════════════════════════════╝{RST}
"""


# ══════════════════════════════════════════════════════════════════════════════
#  SETUP
# ══════════════════════════════════════════════════════════════════════════════

def run_setup():
    print(f"\n{Y}=== First-run Family Setup ==={RST}\n")

    members_input = input("Enter family members, comma-separated (e.g. Mom,Dad,Emma,Jake): ").strip()
    names = [n.strip() for n in members_input.split(",") if n.strip()]

    if not names:
        print(f"{R}No names entered. Exiting setup.{RST}")
        return

    for name in names:
        role = "parent" if name.lower() in ("mom","dad","mother","father") else "child"
        print(f"\n{C}Setting up {name} ({role}){RST}")
        prefs_raw = input(f"  Any preferences for {name}? (e.g. likes hiking, hates jazz): ").strip()
        diet_raw  = input(f"  Dietary restrictions for {name}? (e.g. nut allergy, vegetarian): ").strip()

        db.upsert_member(
            name        = name,
            role        = role,
            preferences = {"notes": prefs_raw} if prefs_raw else {},
            dietary     = [d.strip() for d in diet_raw.split(",")] if diet_raw else []
        )
        db.add_fae(name, "joined", "Family Fabric", source="setup")
        print(f"  {G}✓ {name} added{RST}")

    # Seed LLM config
    lm_url = input(
        f"\nLM Studio URL [{C}http://localhost:1234/v1{RST}]: "
    ).strip() or "http://localhost:1234/v1"
    lm_model = input("Model name shown in LM Studio [local-model]: ").strip() or "local-model"

    llm.configure(base_url=lm_url, model=lm_model)

    # Test connection
    print(f"\n{DIM}Testing LM Studio connection...{RST}")
    if llm.ping():
        print(f"{G}✓ LM Studio is reachable!{RST}")
    else:
        print(f"{Y}⚠  LM Studio not reachable at {lm_url}{RST}")
        print(f"   Start LM Studio, load a model, then run main.py again.")

    print(f"\n{G}Setup complete! Run: python main.py{RST}\n")


# ══════════════════════════════════════════════════════════════════════════════
#  AGENT CHAT LOOP
# ══════════════════════════════════════════════════════════════════════════════

def member_chat_loop(agent: object, master: object):
    name = agent.name
    print(f"\n{C}── {name}'s chat ─────────────────────────────────────{RST}")
    print(f"{DIM}  (type 'back' to return to menu, 'quit' to exit){RST}\n")

    # Deliver any pending nudges as a ONE-TIME opening greeting
    pending = db.get_pending_messages(f"agent_{name.lower()}")
    if pending:
        try:
            # Collect and mark ALL nudges delivered BEFORE generating the greeting
            # so they never appear in the system prompt again after this moment
            nudge_texts = []
            for msg in pending:
                import json as _j
                payload = _j.loads(msg["payload"])
                text = payload.get("message", "").strip()
                if text:
                    nudge_texts.append(text)
                db.mark_message_delivered(msg["id"])
            agent._pending_nudges.clear()

            if nudge_texts:
                nudge_summary = " | ".join(nudge_texts)
                greeting = agent.chat(
                    f"[one-time delivery] Greet {name} and mention this naturally in 1-2 sentences "
                    f"(do NOT repeat it again later): {nudge_summary}"
                )
                print(f"{C}AI ({name}){RST}: {greeting}\n")
                master.process_agent_reports()
        except ConnectionError as e:
            print(f"{R}{e}{RST}\n")
        except Exception as e:
            print(f"{R}[Error] {e}{RST}\n")

    while True:
        try:
            user_input = input(f"{Y}{name}{RST}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue
        if user_input.lower() in ("back", "menu"):
            break
        if user_input.lower() in ("quit", "exit", "q"):
            sys.exit(0)

        try:
            reply = agent.chat(user_input)
            print(f"{C}AI ({name}){RST}: {reply}\n")

            # After each exchange, let master check if any cross-family nudges are needed
            master.process_agent_reports()

        except ConnectionError as e:
            print(f"{R}{e}{RST}\n")
        except Exception as e:
            print(f"{R}[Error] {e}{RST}\n")


# ══════════════════════════════════════════════════════════════════════════════
#  MASTER CONSOLE
# ══════════════════════════════════════════════════════════════════════════════

def master_console(master: object):
    print(f"\n{M}── Master Console ────────────────────────────────────{RST}")
    print(f"{DIM}Commands: chat, nudge, relay, reflect, status, faes, chores, grocery, back{RST}\n")

    members = db.get_members()
    member_names = [m["name"] for m in members]

    while True:
        try:
            raw = input(f"{M}master>{RST} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue
        cmd_parts = raw.split(None, 1)
        cmd = cmd_parts[0].lower()
        rest = cmd_parts[1] if len(cmd_parts) > 1 else ""

        # ── back / quit ──────────────────────────────────────────────────
        if cmd in ("back", "menu"):
            break
        if cmd in ("quit", "exit", "q"):
            sys.exit(0)

        # ── status ───────────────────────────────────────────────────────
        elif cmd == "status":
            s = master.status()
            print(f"\n{C}Family Status{RST}")
            print(f"  Members:        {', '.join(s['members'])}")
            print(f"  Recent FAEs:    {s['recent_faes']}")
            print(f"  Pending chores: {s['pending_chores']}")
            print(f"  Grocery items:  {s['grocery_items']}")
            print(f"  Bus messages:   {s['bus_messages']}")
            print()

        # ── faes ─────────────────────────────────────────────────────────
        elif cmd == "faes":
            member_filter = rest.strip() if rest else None
            faes = db.get_faes(member=member_filter, limit=20)
            print(f"\n{C}Recent FAEs{RST}" + (f" ({member_filter})" if member_filter else ""))
            if not faes:
                print("  (none)")
            for f in faes:
                ts = f["timestamp"][:16]
                print(f"  {DIM}{ts}{RST}  {Y}{f['member']}{RST} {f['action']} {W}{f['activity']}{RST}")
                if f.get("detail") and f["detail"] != f["activity"]:
                    print(f"           {DIM}{f['detail'][:80]}{RST}")
            print()

        # ── nudge <Member> <message> ──────────────────────────────────────
        elif cmd == "nudge":
            # nudge Mom Hey, Dad's golfing Saturday
            parts = rest.split(None, 1)
            if len(parts) < 2:
                print(f"{Y}Usage: nudge <MemberName> <message>{RST}")
            else:
                target, msg = parts[0], parts[1]
                if target not in member_names:
                    print(f"{R}Unknown member: {target}. Members: {member_names}{RST}")
                else:
                    mid = master.nudge(target, msg)
                    print(f"{G}✓ Nudge queued for {target}'s agent (id: {mid}){RST}")
                    print(f"  Will be delivered next time {target} chats.\n")

        # ── relay <FromMember> <ToMember> <message> ───────────────────────
        elif cmd == "relay":
            # relay Dad Mom I'm planning to golf Saturday
            parts = rest.split(None, 2)
            if len(parts) < 3:
                print(f"{Y}Usage: relay <From> <To> <message>{RST}")
            else:
                frm, to_, msg = parts
                if frm not in member_names or to_ not in member_names:
                    print(f"{R}Unknown member. Members: {member_names}{RST}")
                else:
                    nudge_text = master.relay(frm, to_, msg)
                    print(f"{G}✓ Relayed. {to_}'s agent will say:{RST}")
                    print(f"  \"{nudge_text}\"\n")

        # ── reflect ───────────────────────────────────────────────────────
        elif cmd == "reflect":
            print(f"{DIM}Running master reflection...{RST}")
            try:
                result = master.reflect()
                dispatched, analysis = result if isinstance(result, tuple) else (result, "")
                if analysis:
                    print(f"\n{C}Analysis:{RST} {analysis[:300]}\n")
                if dispatched:
                    print(f"{G}Nudges dispatched:{RST}")
                    for d in dispatched:
                        print(f"  → {d}")
                else:
                    print(f"{C}No coordination needed right now.{RST}")
                print()
            except ConnectionError as e:
                print(f"{R}{e}{RST}\n")

        # ── chores ────────────────────────────────────────────────────────
        elif cmd == "chores":
            chores = db.get_chores()
            print(f"\n{C}Pending Chores{RST}")
            if not chores:
                print("  (none)")
            for c in chores:
                print(f"  {DIM}{c['id']}{RST}  {Y}{c['member']}{RST}: {c['task']} ({c['frequency']})")
            print()

        # ── grocery ───────────────────────────────────────────────────────
        elif cmd == "grocery":
            items = db.get_grocery()
            print(f"\n{C}Grocery List{RST}")
            if not items:
                print("  (empty)")
            last_cat = None
            for item in items:
                if item["category"] != last_cat:
                    print(f"  {DIM}── {item['category']} ──{RST}")
                    last_cat = item["category"]
                print(f"    □ {item['item']} ({item['qty']})")
            print()

        # ── free chat (pass to master LLM) ────────────────────────────────
        elif cmd == "chat" or cmd not in (
            "status","faes","nudge","relay","reflect","chores","grocery"
        ):
            query = rest if cmd == "chat" else raw
            # Strip accidental backtick blocks before sending
            query = query.strip().strip("`").strip()
            if not query:
                print(f"{Y}Usage: chat <your question>{RST}")
                continue
            try:
                reply = master.chat(query)
                print(f"\n{M}Master{RST}: {reply}\n")
            except ConnectionError as e:
                print(f"{R}{e}{RST}\n")

        else:
            print(f"{Y}Unknown command: {cmd}{RST}")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN MENU
# ══════════════════════════════════════════════════════════════════════════════

def main_menu(agents: dict, master: object):
    members = list(agents.keys())

    while True:
        print(f"\n{C}╔══ Family Fabric ══════════════════════════╗{RST}")
        for i, name in enumerate(members, 1):
            # Show if they have pending nudges
            pending = db.get_pending_messages(f"agent_{name.lower()}")
            badge = f" {Y}[{len(pending)} nudge{'s' if len(pending)>1 else ''}]{RST}" if pending else ""
            print(f"{C}║{RST}  {i}. Chat as {W}{name}{RST}{badge}")
        print(f"{C}║{RST}  m. Master console")
        print(f"{C}║{RST}  q. Quit")
        print(f"{C}╚════════════════════════════════════════════╝{RST}")

        choice = input("Choose: ").strip()

        if choice.lower() in ("q", "quit", "exit"):
            print(f"\n{DIM}Goodbye.{RST}\n")
            sys.exit(0)
        elif choice.lower() in ("m", "master"):
            master_console(master)
        elif choice.isdigit() and 1 <= int(choice) <= len(members):
            name = members[int(choice) - 1]
            member_chat_loop(agents[name], master)
        elif any(choice.lower() == n.lower() for n in members):
            name = next(n for n in members if n.lower() == choice.lower())
            member_chat_loop(agents[name], master)
        else:
            opts = ", ".join(f"{idx+1}={n}" for idx,n in enumerate(members))
            print(f"{Y}Options: {opts}, m=master, q=quit{RST}")


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Family Fabric CLI")
    parser.add_argument("--setup",  action="store_true", help="Run first-time setup")
    parser.add_argument("--member", type=str,            help="Jump into a member's chat")
    parser.add_argument("--master", action="store_true", help="Jump into master console")
    args = parser.parse_args()

    # Import agents here (inside main) to avoid circular import at module load
    from agents.personal_agent import PersonalAgent
    from agents.master import MasterOrchestrator

    # Init DB always
    db.init_db()

    # ── Setup mode ──────────────────────────────────────────────────────────
    if args.setup:
        run_setup()
        return

    # ── Check we have members ────────────────────────────────────────────────
    members = db.get_members()
    if not members:
        print(f"\n{Y}No family members found. Run setup first:{RST}")
        print(f"  python main.py --setup\n")
        return

    print(BANNER)

    # ── Check LM Studio ─────────────────────────────────────────────────────
    if not llm.ping():
        print(f"{Y}⚠  LM Studio not detected at http://localhost:1234/v1{RST}")
        print(f"   Start LM Studio and load a model, then press Enter to continue.")
        print(f"   (Or edit core/llm.py to point to Ollama or another provider)\n")
        input("Press Enter when ready (or Ctrl+C to quit)...")

    # ── Build agent roster ───────────────────────────────────────────────────
    agents: dict[str, PersonalAgent] = {}
    for m in members:
        agents[m["name"]] = PersonalAgent(m["name"])

    master = MasterOrchestrator(agents)

    print(f"{G}✓ Loaded {len(agents)} agents: {', '.join(agents.keys())}{RST}")
    print(f"{DIM}  Tip: Master can nudge any agent — they'll tell their person naturally.{RST}\n")

    # ── Jump modes ───────────────────────────────────────────────────────────
    if args.master:
        master_console(master)
        return

    if args.member:
        if args.member not in agents:
            print(f"{R}Unknown member: {args.member}{RST}")
            print(f"Known: {list(agents.keys())}")
            return
        member_chat_loop(agents[args.member], master)
        return

    # ── Full interactive menu ────────────────────────────────────────────────
    try:
        main_menu(agents, master)
    except KeyboardInterrupt:
        print(f"\n\n{DIM}Interrupted. Goodbye.{RST}\n")


if __name__ == "__main__":
    main()