# 🏠 Family Fabric

A local AI system that gives every family member their own personal AI agent — and a Master Orchestrator that watches everything and quietly coordinates between them.

No cloud. No subscriptions. Runs on your machine with LM Studio.

---

## What It Does

Each family member gets a private 1-on-1 chat with their own AI agent. The agent knows their preferences, dietary needs, and recent family activity. It talks like a helpful friend — short, casual, no robot dashboards.

Behind the scenes, a **Master Orchestrator** reads everything happening across all agents. When it spots something useful — a scheduling conflict, info one person shared that another should know — it sends a **nudge** to the right agent, who slips it into conversation naturally.

```
          ┌──────────────────┐
          │  MASTER (you)    │  ← sees everything, sends nudges
          └────────┬─────────┘
       ┌───────────┼───────────┐
  ┌────▼───┐  ┌────▼───┐  ┌───▼────┐
  │ agent  │  │ agent  │  │ agent  │  ← one per person
  │  Mom   │  │  Dad   │  │ Logan  │
  └────┬───┘  └────┬───┘  └───┬────┘
      Mom          Dad       Logan     ← each in their own chat
```

**Example nudge flow:**
```
Master console:
  nudge dad Mom is planning tacos this weekend

        ↓  queued silently on message bus

Dad opens his chat:
  AI: Hey! By the way, mom mentioned she's making tacos this weekend.

Dad: nice, I'll pick up stuff at the store
  AI: Perfect, I can help you make a list.
```

The agent never says "I received a nudge" or exposes any system internals.

---

## Requirements

- **Python 3.10+**
- **[LM Studio](https://lmstudio.ai)** running locally with a model loaded
  - Works with any model: Llama 3, Qwen, Mistral, Phi, etc.
  - Default endpoint: `http://localhost:1234/v1`
- **No external Python packages** — pure stdlib only

---

## Quick Start

```powershell
# 1. First-time setup — add family members, test LM Studio connection
python main.py --setup

# 2. Run
python main.py
```

### Optional jump modes
```powershell
python main.py --member Mom     # go straight into Mom's chat
python main.py --master         # go straight to master console
```

---

## File Structure

```
family AI core/
├── main.py                  # Entry point, CLI, menus, chat loops
├── core/
│   ├── db.py               # SQLite database — FAEs, message bus, members, chores, grocery
│   └── llm.py              # LM Studio client (OpenAI-compatible)
├── agents/
│   ├── personal_agent.py   # PersonalAgent — 1-on-1 chat, nudge delivery, FAE extraction
│   └── master.py           # MasterOrchestrator — watches all agents, sends nudges
└── data/
    └── family_fabric.db    # Created automatically on first run
```

---

## Menu Navigation

At the main menu you can type a **number**, a **name**, or a **command**:

```
╔══ Family Fabric ══════════════════════════╗
║  1. Chat as Earl
║  2. Chat as dad  [1 nudge]               ← pending nudge badge
║  3. Chat as feed
║  m. Master console
║  q. Quit
╚════════════════════════════════════════════╝
Choose: dad        ← numbers, names, or m/q all work
```

Inside any chat: type `back` to return to the menu, `quit` to exit.

**Nudge badges** — if a family member has a pending nudge when they open their chat, their agent will greet them and work it in naturally before waiting for input.

---

## Master Console Commands

Access with `m` from the main menu.

| Command | What it does |
|---|---|
| `status` | Overview: members, FAE count, chores, grocery, bus messages |
| `faes` | Recent Family Atomic Events — everything logged across all members |
| `faes Mom` | FAEs filtered to one member |
| `nudge Dad Hey, mom's making tacos Saturday` | Queue a message to Dad's agent — delivered naturally next time he chats |
| `relay Mom Dad I want to go to the craft fair Sunday` | Master frames it naturally, then nudges Dad's agent |
| `reflect` | Master scans all real FAEs and auto-nudges where coordination would help |
| `chores` | Show pending chore assignments |
| `grocery` | Show grocery list |
| `chat <question>` | Ask master anything about the family's state |
| `back` | Return to main menu |

---

## How the Pieces Work

### Family Atomic Events (FAEs)
Every meaningful thing said in any chat is logged as a minimal structured fact:

```
Mom  expressed_interest  I want to make tacos this weekend
Dad  planned             going to Jeff's house Friday night
Logan needs              help with math homework
```

These flow into the Master's view so it can spot patterns and coordination needs without reading full conversation transcripts.

### Message Bus
All communication between agents goes through a SQLite message bus — no direct function calls between agents. Master posts a nudge, agent picks it up next time that person chats. This keeps agents fully independent.

### Personal Agent
Each agent:
- Keeps its own private conversation history (only that member's turns)
- Checks the message bus for nudges before every reply
- Delivers nudges as a natural opening greeting if they're waiting when the person enters chat
- Extracts FAEs from what the person says and reports them to master
- Knows the member's preferences and dietary needs from setup

### Master Orchestrator
- Sees all FAEs from all agents
- `reflect` scans real events only — never invents
- `relay` uses a separate plain-text prompt so it never outputs JSON blobs
- Dispatches nudges via the bus — agents deliver them, master never talks directly to members

---

## Changing the LLM

Edit `core/llm.py` — change `BASE_URL` and `MODEL`:

```python
# Ollama
BASE_URL = "http://localhost:11434/v1"
MODEL    = "qwen2.5:7b"

# OpenAI
BASE_URL = "https://api.openai.com/v1"
MODEL    = "gpt-4o-mini"
```

Larger models (13B+) follow the "say it once, don't repeat" instructions much more reliably than 7-8B models.

---

## Known Behaviours

- **Smaller models (7-8B)** may still occasionally re-mention nudge content across turns. Larger models handle this much better.
- **`reflect`** works best after several real conversations have happened so there are meaningful FAEs to analyze.
- **Grocery and chores** are tracked in the DB but currently require master console commands to manage — member agents can log intent but don't yet directly write to the lists.

---

## Roadmap

- [ ] Member agents can directly add grocery items and chores when asked
- [ ] Member asks agent to tell someone something → auto-routes through master
- [ ] Google Calendar sync
- [ ] Scheduled reflect (cron / background thread)
- [ ] Per-member terminal windows (run `--member Mom` in separate PowerShell tabs)
- [ ] Homework tutor mode (kid-safe, progress tracked)
- [ ] Voice input via `whisper.cpp`
