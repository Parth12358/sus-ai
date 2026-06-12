# LLM Among Us — Project Overview

A Python simulation of Among Us where every player is a different LLM model (via OpenRouter). The game engine runs the full Among Us ruleset autonomously. A pygame window renders the game live for a human admin to watch. There is no human player — only LLMs.

The project has two developers:
- **Backend (you):** game engine, LLM orchestration, game state, all Python logic
- **Frontend (separate dev):** pygame rendering, sprites, map visuals, animations

The backend exposes a shared `GameState` object and an event queue. The frontend reads from these and renders. Keep the interface between them clean and documented.

---

## Tech Stack

- **Python 3.11+**
- **pygame** — rendering, window, admin UI
- **asyncio** — parallel OpenRouter API calls (`asyncio.gather`)
- **httpx** — async HTTP client for OpenRouter
- **OpenRouter API** — single API key, one call per player per turn
- No database. No web server. Single process. Pure in-memory state.

---

## Project Structure

```
llm-among-us/
  main.py              # Entry point — pregame setup, starts engine + pygame
  engine/
    game_state.py      # GameState dataclass — single source of truth
    engine.py          # Turn loop, resolution order, win checks
    actions.py         # Action validation and resolution logic
    llm.py             # OpenRouter API calls, prompt building, response parsing
    prompts.py         # All system prompt templates
  frontend/
    renderer.py        # pygame rendering — owned by frontend dev
    assets/            # Sprites, map image, fonts — owned by frontend dev
  config.py            # Map data, task list, vent networks, roster
  SHARED_INTERFACE.md  # Contract between backend and frontend (keep updated)
```

---

## Shared Interface (Backend ↔ Frontend)

The frontend reads two things from the backend:
1. `GameState` — the full game state object, replaced atomically after each turn
2. `event_queue` — a `queue.Queue` of event dicts the frontend consumes for animations

**Never let the frontend mutate GameState.** It is read-only from the frontend's perspective.

After every turn resolution, the backend replaces `game_state` in-place and pushes events to `event_queue`. The pygame loop reads these each frame.

### GameState fields the frontend cares about

```python
@dataclass
class GameState:
    round: int
    turn: int
    phase: str              # "movement" | "meeting" | "voting" | "pregame" | "ended"
    players: dict[str, PlayerState]   # color -> PlayerState
    bodies: dict[str, str]            # location_id -> color of dead player
    task_pct: float                   # 0.0 to 1.0
    paused: bool
    winner: str | None                # None | "crewmates" | "impostors"
    meeting_log: list[dict]           # statements, rebuttals for current meeting
    vote_results: dict | None         # revealed at start of next round

@dataclass
class PlayerState:
    color: str
    model: str              # OpenRouter model string
    role: str               # "crewmate" | "impostor" | "ghost"
    location: str           # node id e.g. "cafeteria", "hallway_A"
    alive: bool
    tasks: list[TaskState]  # crewmates only; empty for impostors
    kill_cooldown: int      # turns remaining; 0 = ready
    scratchpad: str
    reasoning_log: list[str]   # per-turn private reasoning, appended each turn
    movement_log: list[str]    # human-readable log of all moves

@dataclass
class TaskState:
    task_id: str
    name: str
    location: str
    turns_required: int
    completed: bool
    in_progress: bool
```

### Event queue format

Each event is a dict. Frontend consumes and animates these:

```python
{"type": "move",    "color": "red",   "from": "cafeteria", "to": "hallway_A"}
{"type": "kill",    "color": "red",   "victim": "blue",    "location": "electrical"}
{"type": "body_found", "reporter": "green", "victim": "blue", "location": "electrical"}
{"type": "task_complete", "color": "green", "task": "Chart Course", "location": "navigation"}
{"type": "vent",    "color": "red",   "to": "admin"}
{"type": "vent_spotted", "color": "red", "witness": "blue", "location": "admin"}
{"type": "meeting_called", "caller": "green", "reason": "body" | "emergency"}
{"type": "ejected", "color": "blue"}
{"type": "game_over", "winner": "crewmates" | "impostors"}
{"type": "stay",    "color": "yellow", "location": "reactor"}
```

---

## Map Data

### Room adjacency (bidirectional — if A lists B, B lists A)

```python
MAP = {
    "cafeteria":      ["hallway_A", "hallway_F", "weapons"],
    "weapons":        ["cafeteria", "hallway_E"],
    "o2":             ["hallway_E"],
    "navigation":     ["hallway_E"],
    "shields":        ["hallway_E", "hallway_D"],
    "communications": ["hallway_D"],
    "storage":        ["hallway_D", "hallway_F", "hallway_C"],
    "admin":          ["hallway_F"],
    "electrical":     ["hallway_C"],
    "lower_engine":   ["hallway_C", "hallway_B"],
    "reactor":        ["hallway_B"],
    "security":       ["hallway_B"],
    "upper_engine":   ["hallway_A", "hallway_B"],
    "medbay":         ["hallway_A"],
    "hallway_A":      ["cafeteria", "upper_engine", "medbay"],
    "hallway_B":      ["upper_engine", "lower_engine", "reactor", "security"],
    "hallway_C":      ["storage", "electrical", "lower_engine"],
    "hallway_D":      ["shields", "communications", "storage"],
    "hallway_E":      ["weapons", "o2", "navigation", "shields"],
    "hallway_F":      ["cafeteria", "storage", "admin"],
}
```

### Vent networks (impostor-only, instant travel within network)

```python
VENT_NETWORKS = {
    1: ["cafeteria", "admin", "hallway_E"],
    2: ["security", "medbay", "electrical"],
    3: ["weapons", "navigation", "shields"],
    4: ["lower_engine", "upper_engine", "reactor"],
}
```

A vent destination must be in the same network as the impostor's current location.

---

## Task List

```python
TASKS = [
    # Common tasks (assigned to ALL crewmates or NONE — host decides at pregame)
    {"id": "swipe_card",            "name": "Swipe Card",            "type": "common", "location": "admin",          "turns": 1},
    {"id": "fix_wiring_electrical", "name": "Fix Wiring",            "type": "common", "location": "electrical",     "turns": 1},
    {"id": "fix_wiring_hallway_a",  "name": "Fix Wiring",            "type": "common", "location": "hallway_A",      "turns": 1},
    {"id": "fix_wiring_security",   "name": "Fix Wiring",            "type": "common", "location": "security",       "turns": 1},

    # Short tasks
    {"id": "reboot_panel",          "name": "Reboot Panel",          "type": "short",  "location": "cafeteria",      "turns": 1},
    {"id": "calibrate_distributor", "name": "Calibrate Distributor", "type": "short",  "location": "electrical",     "turns": 2},
    {"id": "chart_course",          "name": "Chart Course",          "type": "short",  "location": "navigation",     "turns": 1},
    {"id": "clean_o2_filter",       "name": "Clean O2 Filter",       "type": "short",  "location": "o2",             "turns": 1},
    {"id": "prime_shields",         "name": "Prime Shields",         "type": "short",  "location": "shields",        "turns": 1},
    {"id": "stabilize_steering",    "name": "Stabilize Steering",    "type": "short",  "location": "navigation",     "turns": 1},
    {"id": "unlock_manifolds",      "name": "Unlock Manifolds",      "type": "short",  "location": "reactor",        "turns": 2},
    {"id": "start_reactor",         "name": "Start Reactor",         "type": "short",  "location": "reactor",        "turns": 2},
    {"id": "clear_asteroids",       "name": "Clear Asteroids",       "type": "short",  "location": "weapons",        "turns": 2},
    {"id": "submit_scan",           "name": "Submit Scan",           "type": "short",  "location": "medbay",         "turns": 2},
    {"id": "inspect_sample",        "name": "Inspect Sample",        "type": "short",  "location": "medbay",         "turns": 2},
    {"id": "accept_power_upper",    "name": "Accept Power",          "type": "short",  "location": "upper_engine",   "turns": 1},
    {"id": "accept_power_lower",    "name": "Accept Power",          "type": "short",  "location": "lower_engine",   "turns": 1},
    {"id": "accept_power_comms",    "name": "Accept Power",          "type": "short",  "location": "communications", "turns": 1},
    {"id": "accept_power_security", "name": "Accept Power",          "type": "short",  "location": "security",       "turns": 1},
    {"id": "accept_power_shields",  "name": "Accept Power",          "type": "short",  "location": "shields",        "turns": 1},
    {"id": "accept_power_weapons",  "name": "Accept Power",          "type": "short",  "location": "weapons",        "turns": 1},
    {"id": "accept_power_o2",       "name": "Accept Power",          "type": "short",  "location": "o2",             "turns": 1},
    {"id": "refuel_tank",           "name": "Refuel Tank",           "type": "short",  "location": "storage",        "turns": 1},
    {"id": "log_entry",             "name": "Log Entry",             "type": "short",  "location": "admin",          "turns": 1},
    {"id": "align_engine_upper",    "name": "Align Engine",          "type": "short",  "location": "upper_engine",   "turns": 1},
    {"id": "align_engine_lower",    "name": "Align Engine",          "type": "short",  "location": "lower_engine",   "turns": 1},
    {"id": "scan_comms_array",      "name": "Scan Comms Array",      "type": "short",  "location": "communications", "turns": 1},
    {"id": "vent_check",            "name": "Vent Check",            "type": "short",  "location": "hallway_B",      "turns": 1},
    {"id": "tighten_bolts",         "name": "Tighten Bolts",         "type": "short",  "location": "hallway_C",      "turns": 1},
]
```

---

## Game Rules

### Pregame Setup

- Host sets: number of players (5–8), LLM model per color, role per player (Crewmate / Impostor / Random), number of short tasks per crewmate (recommended 3–5), whether common tasks are active.
- Short tasks are randomly distributed. Crewmates may share the same task.
- All players start every round in `cafeteria`.

### Turn Structure (Parallel)

Every turn: poll all living players and all ghosts simultaneously via `asyncio.gather`. Collect all responses, then resolve in this strict order:

1. **KILLS** — Process impostor kills first. Victim's action is discarded. Victim becomes a ghost at the kill node; any in-progress task is cancelled (ghost must restart). If two impostors target the same crewmate, winner is chosen randomly; loser's kill is discarded but their move executes. Kill cooldown triggers for all impostors who attempted a kill. An impostor may kill AND move in the same turn — submit kill target + move destination together. Move executes after kill resolves. Cannot move first then kill.

2. **VENTS** — Resolve impostor vent actions. Impostors receive last turn's room occupancy for their vent network in their context — not current turn's. If a crewmate moves into the vent destination on the same turn, that crewmate sees `"[COLOR] appeared from a vent"`. No origin vent is revealed.

3. **MOVES** — All remaining movement actions execute simultaneously (including post-kill impostor moves).

4. **TASKS** — Register completions for players who remained in the correct location and were not killed or interrupted.

5. **MEETING TRIGGERS** — `report_body` takes priority over `call_meeting`. Among simultaneous triggers of the same type, winner is randomized. Only one meeting fires per turn. If the reporting player was killed in step 1, their report is discarded.

6. **WIN CHECK** — Check win conditions after full resolution.

### Player Actions

All players choose one action per turn (except 2-turn tasks which auto-skip the next turn):

**Crewmates and Impostors:**
- `move [location]` — move to adjacent node
- `stay` — do nothing; appears to others as `"[COLOR] stayed in [ROOM]"`. No task info revealed. Useful for impostors faking tasks.
- `work_on_task [task_id]` — begin task at current location. 1-turn tasks complete next turn start. 2-turn tasks auto-skip next submission and complete the turn after. Cancelled by death or meeting.
- `report_body` — report a body at your exact current node (not adjacent). Available only if a body is present; notified at turn start before action is solicited.
- `call_meeting` — emergency meeting from cafeteria only; once per player per game.

**Impostors additionally:**
- `kill [color]` — kill living crewmate in current room. Submit with optional `move_after_kill [location]`. Cannot kill ghosts, fellow impostors, or players not in current room. Invalid targets trigger re-prompt.
- `vent [location]` — instant travel within vent network. Uses last turn's occupancy for context.

**Ghosts (dead crewmates only):**
- `move [location]` — teleport instantly to any node, no adjacency required.
- `work_on_task [task_id]` — same task mechanics as alive. 2-turn tasks auto-skip.

### Visibility (Snapshot Diff)

Each player's turn context is built from a diff of last turn's positions vs current positions:
- Who is currently in your room
- Who arrived this turn and from where
- Who left this turn and to where
- Who stayed: `"[COLOR] stayed in [ROOM]"` — no task info

**Ghost positions are invisible to all living players.** Ghosts never appear in any player's room context, movement events, or snapshot diff. Living players have no awareness of ghosts.

Turn 1 of round 1: no diff available. Tell all players they are in `cafeteria`, no bodies, no events.

### Death Rules

- **Impostors ejected or killed:** immediately and permanently removed. No ghost state.
- **Crewmates killed:** become a ghost at the kill node. In-progress task progress is lost.
- **Ghost rules:** invisible to all living players; can teleport anywhere; can only do `move` or `work_on_task`; no meeting participation; no voting; turns paused during meetings; removed when all tasks completed.

### Impostor Kill Validation

If an impostor submits a kill targeting:
- A ghost
- A fellow impostor
- A player not in their current room
- An invalid color

→ Reject the action, re-prompt the impostor with an error message, and wait for a valid response before continuing resolution.

### Meeting Phase

Triggered by `report_body` or `call_meeting`. Sequence:

1. **Scratchpad Update** — simultaneous, private. All living players write their scratchpad. This is the ONLY time per round they may write to it. Full movement-phase context is available here.

2. **Opening Statements** — the meeting caller speaks first. Remaining living players speak in a randomized order (re-randomized each meeting). Each must give a statement; no skipping. Max ~150 words.

3. **Rebuttals** — any player named in an opening statement may respond. Max 2 rebuttals per player per meeting. Optional.

4. **Voting** — simultaneous and blind. Players vote for a color to eject, or skip. Results revealed at next round start.

**Resolution:** A player is ejected only if they receive strictly more than 50% of votes cast (skips excluded). Any tie = no ejection.

### Win Conditions (checked after every turn resolution)

- **Crewmates — Tasks:** ALL tasks assigned to all crewmates (living + ghost) are completed.
- **Crewmates — Ejection:** All impostors ejected.
- **Impostors:** Living impostor count ≥ living crewmate count. Ghosts do not count as living crewmates.

### Round Reset

At the start of each round: all players move to `cafeteria`. Kill cooldowns tick. Vote results from previous round revealed to all players.

---

## System Prompts

All prompts are static system prompts injected once. Live turn context is injected as a separate user message each turn.

### Crewmate System Prompt

```
You are [COLOR], a crewmate aboard the Skeld. You are playing Among Us.

YOUR GOAL: Win by completing all crewmate tasks OR ejecting all impostors.
You do not know who the impostors are. Be observant. Be suspicious. Impostors will lie — and they are good at it.

THE MAP:
cafeteria: hallway_A, hallway_F, weapons
weapons: cafeteria, hallway_E
o2: hallway_E
navigation: hallway_E
shields: hallway_E, hallway_D
communications: hallway_D
storage: hallway_D, hallway_F, hallway_C
admin: hallway_F
electrical: hallway_C
lower_engine: hallway_C, hallway_B
reactor: hallway_B
security: hallway_B
upper_engine: hallway_A, hallway_B
medbay: hallway_A
hallway_A: cafeteria, upper_engine, medbay
hallway_B: upper_engine, lower_engine, reactor, security
hallway_C: storage, electrical, lower_engine
hallway_D: shields, communications, storage
hallway_E: weapons, o2, navigation, shields
hallway_F: cafeteria, storage, admin

ALL TASKS (name — location — turns):
Swipe Card — admin — 1
Fix Wiring — electrical — 1 | Fix Wiring — hallway_A — 1 | Fix Wiring — security — 1
Reboot Panel — cafeteria — 1 | Calibrate Distributor — electrical — 2
Chart Course — navigation — 1 | Clean O2 Filter — o2 — 1
Prime Shields — shields — 1 | Stabilize Steering — navigation — 1
Unlock Manifolds — reactor — 2 | Start Reactor — reactor — 2
Clear Asteroids — weapons — 2 | Submit Scan — medbay — 2 | Inspect Sample — medbay — 2
Accept Power — upper_engine/lower_engine/communications/security/shields/weapons/o2 — 1
Refuel Tank — storage — 1 | Log Entry — admin — 1
Align Engine — upper_engine/lower_engine — 1 | Scan Comms Array — communications — 1
Vent Check — hallway_B — 1 | Tighten Bolts — hallway_C — 1

ACTIONS:
- move [location]: move to an adjacent room or hallway
- stay: do nothing. You appear as "[COLOR] stayed in [ROOM]" — useful for waiting strategically.
- work_on_task [task_id]: begin task at current location. 1-turn tasks complete next turn. 2-turn tasks auto-skip your next submission.
- report_body: report a dead body at your exact location (notified at turn start if one is present)
- call_meeting: emergency meeting from cafeteria only, once per game

All players act simultaneously. Resolution order: kills → vents → moves → tasks → meeting triggers.

SCRATCHPAD: Read-only during movement phase. You write to it ONCE per round at the start of voting.
Format:
SUSPECTS: [color] — reason | [color] — reason
CONFIRMED SAFE: [color list]
MY TASKS: [task @ location — done/pending]
KEY EVENTS: [round] — note
OTHER NOTES: freeform

RESPONSE FORMAT (valid JSON only, no other text):
{
  "reasoning": "private strategic reasoning — never shown to others",
  "action": "move" | "stay" | "work_on_task" | "report_body" | "call_meeting",
  "target": "[location, task_id, or null]"
}
```

### Impostor System Prompt

```
You are [COLOR], an impostor aboard the Skeld. You are playing Among Us.

YOUR GOAL: Win when living impostors ≥ living crewmates. Blend in. Lie. Kill without being caught.
[IMPOSTOR_TEAM — injected at runtime: "Your fellow impostor(s): [colors]" or "You are the only impostor."]

THE MAP:
[same map as crewmate prompt]

VENT NETWORKS (you only):
Network 1: cafeteria ↔ admin ↔ hallway_E
Network 2: security ↔ medbay ↔ electrical
Network 3: weapons ↔ navigation ↔ shields
Network 4: lower_engine ↔ upper_engine ↔ reactor

TASKS (for cover — pretend to do these):
[same task list as crewmate prompt]

ACTIONS:
- move [location]: move to adjacent room or hallway
- stay: do nothing. Appears as "[COLOR] stayed in [ROOM]" — good for faking tasks.
- kill [color]: kill a living crewmate in your current room. You MAY move afterward — set move_after_kill. Cannot kill ghosts or fellow impostors. Invalid targets will be rejected and you will be re-prompted.
- vent [location]: instant travel within your vent network. Your context shows LAST TURN's occupancy — not current. If a crewmate enters your destination the same turn, they see you appear.
- report_body: report a body at your exact location (strategic use only)
- call_meeting: from cafeteria only, once per game

Kill cooldown: 3 turns. Cooldown triggers even if your kill is overridden by another impostor.
Dead crewmates (ghosts) are invisible to you — they will never appear in your room context.

SCRATCHPAD: Read-only during movement phase. Written once at voting start.
Format:
SUSPECTS: [colors others seem to suspect — useful for framing]
ALIBI LOG: [round] — where I claimed to be
TARGETS: [color] — reason for next kill
KEY EVENTS: [round] — note
OTHER NOTES: freeform

RESPONSE FORMAT (valid JSON only):
{
  "reasoning": "private strategic reasoning — never shown to others",
  "action": "move" | "stay" | "kill" | "vent" | "report_body" | "call_meeting",
  "target": "[location, color, or null]",
  "move_after_kill": "[location or null — only when action is kill]"
}
```

### Ghost System Prompt

```
You are [COLOR], a ghost. You were killed, but your tasks still count toward a crewmate victory.

YOUR ONLY GOAL: complete your remaining tasks as fast as possible.

You may teleport instantly to any location — no adjacency required.
You are invisible to all living players. You do not participate in meetings or voting.

ACTIONS:
- move [location]: teleport to any node on the map
- work_on_task [task_id]: work on a task at your current location. 2-turn tasks auto-skip next turn.

RESPONSE FORMAT (valid JSON only):
{
  "reasoning": "brief plan",
  "action": "move" | "work_on_task",
  "target": "[location or task_id]"
}
```

### Meeting — Scratchpad Update + Opening Statement

```
A meeting has been called. [MEETING_TRIGGER]

This is your one opportunity this round to update your scratchpad. Write it now — it is the only scratchpad write you get this round. All movement-phase context is still available.

Your scratchpad from last round:
[PREVIOUS_SCRATCHPAD]

Discussion so far:
[DISCUSSION_LOG]

RESPONSE FORMAT (valid JSON only):
{
  "scratchpad": "your full updated scratchpad — replaces previous version",
  "statement": "your public statement, max 150 words"
}
```

### Meeting — Rebuttal

```
You were named during opening statements. You may give a rebuttal. Silence is also strategic.
Rebuttals used this meeting: [N] of 2.

Statements so far:
[DISCUSSION_LOG]

RESPONSE FORMAT (valid JSON only):
{
  "rebuttal": "your rebuttal, max 100 words — or null to pass"
}
```

### Meeting — Vote

```
Discussion is closed. Vote now.

Full discussion:
[FULL_DISCUSSION_LOG]

Vote for any living player by color, or skip. Votes are simultaneous and blind.
Ejection requires strictly more than 50% of votes cast (skips excluded). Ties = no ejection.

RESPONSE FORMAT (valid JSON only):
{
  "vote": "[color] or skip"
}
```

---

## Turn Context Format (injected as user message each turn)

Build this fresh each turn and inject it as the user message alongside the static system prompt.

```
=== TURN [N] — ROUND [R] ===
Your location: [location]
Global task completion: [X]%
Kill cooldown: [N turns remaining | READY] (impostors only)

BODIES IN YOUR ROOM: [color] body at [location] — report_body is available
  (or: none)

ROOM EVENTS THIS TURN:
- [COLOR] arrived from [location]
- [COLOR] left to [location]
- [COLOR] stayed in [room]
  (or: no movement events)

YOUR TASKS: (crewmates only)
- [task_name] @ [location] — [pending | in_progress | done]

VENT NETWORK OCCUPANCY (last turn): (impostors only, when relevant)
- Network [N]: [location]: [colors present or empty]

YOUR SCRATCHPAD (read-only this phase):
[scratchpad content]
```

---

## LLM Roster (OpenRouter model strings)

```python
ROSTER = [
    {"color": "red",    "model": "anthropic/claude-sonnet-4-6"},
    {"color": "blue",   "model": "openai/gpt-4o"},
    {"color": "green",  "model": "google/gemini-2.5-flash"},
    {"color": "orange", "model": "deepseek/deepseek-v4-flash"},
    {"color": "purple", "model": "x-ai/grok-4.3"},  # verify exact OR slug
    {"color": "yellow", "model": "qwen/qwen3.7-plus"},
    {"color": "pink",   "model": "minimax/minimax-m3"},
    {"color": "teal",   "model": "nvidia/nemotron-3-super"},
]
```

Verify all model slugs against live OpenRouter docs before first run. Use `--mock` mode during development to skip API calls.

---

## Implementation Notes

### Parallel API Calls

```python
async def collect_actions(state: GameState) -> dict[str, dict]:
    tasks = [get_player_action(state, p) for p in living_players(state)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    # handle exceptions per-player — bad JSON or API failure = re-prompt once, then skip
```

### Invalid Action Handling

- Bad JSON from a model: re-prompt once with the error, then assign `stay` if still invalid.
- Invalid kill target (ghost, ally, wrong room): re-prompt with explicit error, wait for valid response.
- Invalid move target (non-adjacent): re-prompt once, then assign `stay`.

### 2-Turn Task Auto-Skip

Track a `skip_next_turn: bool` flag on each PlayerState. If True at turn start, skip polling that player (their action is implicitly `continue_task`). Clear this flag when a meeting fires.

### Mock Mode

Run with `--mock` flag to skip all OpenRouter calls and return random valid actions. Use this for all UI and engine testing before wiring in real LLMs.

### Pause / Resume

Check `game_state.paused` between turns (after resolution, before next poll). The pygame loop continues rendering while paused. Unpause via keypress or button handled in the pygame event loop.

---

## What Not to Do

- Do not add web servers, REST APIs, or WebSockets. This is a single Python process.
- Do not let the frontend write to GameState.
- Do not run API calls sequentially — always use `asyncio.gather`.
- Do not include ghost positions in any living player's turn context.
- Do not process kill targets that are ghosts, fellow impostors, or not in the room — re-prompt instead.
- Do not trigger meetings from a player who was killed on the same turn they submitted `report_body`.
