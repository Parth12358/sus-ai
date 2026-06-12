# Shared Interface (Backend <-> Frontend)

The frontend reads two things from the backend:
1. `GameState` — the full game state object, replaced atomically after each turn
2. `event_queue` — a `queue.Queue` of event dicts the frontend consumes for animations

**Never let the frontend mutate GameState.** It is read-only from the frontend's perspective.

After every turn resolution, the backend replaces `game_state` in-place and pushes events to `event_queue`. The pygame loop reads these each frame.

## GameState fields the frontend cares about

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
    event_queue: Queue[dict]

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
    skip_next_turn: bool

@dataclass
class TaskState:
    task_id: str
    name: str
    location: str
    turns_required: int
    completed: bool
    in_progress: bool
```

## Event queue format

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
