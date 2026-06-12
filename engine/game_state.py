from dataclasses import dataclass, field
from queue import Queue


@dataclass
class TaskState:
    task_id: str
    name: str
    location: str
    turns_required: int
    completed: bool = False
    in_progress: bool = False


@dataclass
class PlayerState:
    color: str
    model: str
    role: str               # "crewmate" | "impostor" | "ghost"
    location: str
    alive: bool = True
    tasks: list[TaskState] = field(default_factory=list)
    kill_cooldown: int = 0  # turns remaining; 0 = ready
    scratchpad: str = ""
    reasoning_log: list[str] = field(default_factory=list)
    movement_log: list[str] = field(default_factory=list)
    skip_next_turn: bool = False


@dataclass
class GameState:
    round: int = 0
    turn: int = 0
    phase: str = "pregame"  # "pregame" | "movement" | "meeting" | "voting" | "ended"
    players: dict[str, PlayerState] = field(default_factory=dict)
    bodies: dict[str, str] = field(default_factory=dict)    # location -> color
    task_pct: float = 0.0
    paused: bool = False
    winner: str | None = None                                # None | "crewmates" | "impostors"
    meeting_log: list[dict] = field(default_factory=list)
    vote_results: dict | None = None
    event_queue: "Queue[dict]" = field(default_factory=Queue)
