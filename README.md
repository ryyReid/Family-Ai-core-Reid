# 🏠 Family Fabric — CLI

AI-first family coordination system. A **Master Orchestrator** watches all activity,
personal **Agents** talk 1-on-1 with each family member, and the Master can **nudge**
any agent to deliver info to their person naturally — no dashboards, no dashboards.

```
          ┌──────────────┐
          │    MASTER    │  ← admin terminal, sees everything
          │ Orchestrator │
          └──────┬───────┘
        ┌────────┼────────┐
        │        │        │
   ┌────▼──┐ ┌──▼───┐ ┌──▼───┐
   │agent  │ │agent │ │agent │  ← each agent owns 1 conversation
   │ Mom   │ │ Dad  │ │ Emma │
   └────┬──┘ └──┬───┘ └──┬───┘
        │        │        │
      [Mom]    [Dad]    [Emma]   ← family members, each in their own terminal
```

---

## Requirements

- Python 3.10+
- [LM Studio](https://lmstudio.ai) running locally with a model loaded
  - Any model works: Qwen, Llama, Mistral, Phi, etc.
  - Default URL: `http://localhost:1234/v1`
- No external Python packages needed (uses stdlib only)

---

## Quick Start

```bash
# 1. First-time setup (adds family members, tests LM Studio)
python main.py --setup

# 2. Run the system
python main.py

# 3. Optional: jump straight to a person or master
python main.py --member Mom
python main.py --master
```

---

## How It Works

### Personal Agents
Each family member gets their own agent. When they chat, it's a private 1-on-1 conversation.
The agent knows:
- Their preferences and dietary needs
- Recent family activity (FAEs)
- Any nudges queued by the Master

### Master Orchestrator
The Master sees everything. From the master console you can:

| Command | What it does |
|---|---|
| `status` | Family overview: members, FAEs, chores, grocery |
| `faes [Member]` | Show recent Family Atomic Events |
| `nudge Mom Hey, Dad's golfing Saturday` | Queue a message to Mom's agent — she'll hear it naturally next time she chats |
| `relay Dad Mom I'm planning to golf Saturday` | Master frames it naturally, then nudges Mom's agent |
| `reflect` | Master scans all FAEs and auto-nudges where coordination is needed |
| `chores` | Show pending chores |
| `grocery` | Show grocery list |
| `chat <question>` | Ask the master anything about the family |

### The Nudge Flow
```
Master console:
  nudge Mom "Dad is golfing Saturday, heads up"

         ↓  queued on message bus

Mom chats with her agent:
  Mom: "What's going on this weekend?"
  AI:  "Looks pretty open! Oh — just so you know,
        Dad has golf on Saturday. Might be worth
        syncing up on the rest of the weekend."
```
The agent weaves it in naturally — Mom never sees "I received a nudge saying..."

### Family Atomic Events (FAEs)
Every interaction is logged as an FAE — lightweight structured facts:
```
Mom  expressed_interest  Annual Craft Fair
Dad  planned             Golf Game Saturday
Emma needs               help with math homework
```
These flow into the Master's view so it can spot conflicts and opportunities.

---

## File Structure

```
family_fabric/
├── main.py                  # Entry point, CLI, menus
├── core/
│   ├── db.py               # SQLite FMDB + message bus
│   └── llm.py              # LM Studio / OpenAI-compatible client
├── agents/
│   ├── personal_agent.py   # PersonalAgent class
│   └── master.py           # MasterOrchestrator class
└── data/
    └── family_fabric.db    # Created automatically
```

---

## Switching LLM Backend

Edit `core/llm.py` — change `BASE_URL` and `MODEL`:

```python
# Ollama
BASE_URL = "http://localhost:11434/v1"
MODEL    = "qwen2.5:7b"

# OpenAI
BASE_URL = "https://api.openai.com/v1"
MODEL    = "gpt-4o-mini"
```

---

## Roadmap

- [ ] Google Calendar sync (Calendar Agent)
- [ ] Grocery auto-order via Instacart API
- [ ] Scheduled reflect (runs every hour via cron)
- [ ] Per-member terminal sessions (run `--member Mom` in separate windows)
- [ ] Homework tutor mode (kid-safe, tracked progress)
- [ ] Voice input via `whisper.cpp`
