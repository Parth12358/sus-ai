"""Action validation and resolution logic."""

from config import MAP, VENT_NETWORKS
from engine.game_state import GameState, PlayerState


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_action(player: PlayerState, action: dict, state: GameState) -> tuple[bool, str]:
    """Return (ok, error_message). error_message is '' when ok."""
    act = action.get("action", "")
    target = action.get("target")

    if player.role == "ghost":
        if act == "move":
            if target not in MAP:
                return False, f"Unknown location '{target}'."
            return True, ""
        if act == "work_on_task":
            return _validate_task(player, target, state)
        return False, f"Ghosts may only 'move' or 'work_on_task', got '{act}'."

    if act == "move":
        if target not in MAP:
            return False, f"Unknown location '{target}'."
        if target not in MAP.get(player.location, []):
            return False, f"'{target}' is not adjacent to '{player.location}'."
        return True, ""

    if act == "stay":
        return True, ""

    if act == "work_on_task":
        return _validate_task(player, target, state)

    if act == "report_body":
        if player.location not in state.bodies:
            return False, "No body at your current location."
        return True, ""

    if act == "call_meeting":
        if player.location != "cafeteria":
            return False, "Emergency meetings can only be called from the cafeteria."
        if getattr(player, "_used_emergency_meeting", False):
            return False, "You have already used your emergency meeting this game."
        return True, ""

    # Impostor-only actions
    if player.role != "impostor":
        return False, f"Action '{act}' is only available to impostors."

    if act == "kill":
        return _validate_kill(player, target, state)

    if act == "vent":
        return _validate_vent(player, target)

    return False, f"Unknown action '{act}'."


def _validate_task(player: PlayerState, task_id: str, state: GameState) -> tuple[bool, str]:
    task = next((t for t in player.tasks if t.task_id == task_id), None)
    if task is None:
        return False, f"You do not have task '{task_id}'."
    if task.completed:
        return False, f"Task '{task_id}' is already complete."
    if task.location != player.location:
        return False, f"Task '{task_id}' must be done in '{task.location}', you are in '{player.location}'."
    return True, ""


def _validate_kill(player: PlayerState, target_color: str, state: GameState) -> tuple[bool, str]:
    if player.kill_cooldown > 0:
        return False, f"Kill cooldown active: {player.kill_cooldown} turns remaining."
    target = state.players.get(target_color)
    if target is None:
        return False, f"No player with color '{target_color}'."
    if not target.alive:
        return False, f"{target_color} is already dead (ghost). You cannot kill ghosts."
    if target.role == "impostor":
        return False, f"{target_color} is a fellow impostor. You cannot kill impostors."
    if target.location != player.location:
        return False, f"{target_color} is not in your current room."
    return True, ""


def _validate_vent(player: PlayerState, destination: str) -> tuple[bool, str]:
    if destination not in MAP:
        return False, f"Unknown location '{destination}'."
    # Find the network the player is currently in
    current_network = None
    for net_id, nodes in VENT_NETWORKS.items():
        if player.location in nodes:
            current_network = net_id
            break
    if current_network is None:
        return False, f"There is no vent at '{player.location}'."
    if destination not in VENT_NETWORKS[current_network]:
        return False, (
            f"'{destination}' is not in your vent network (Network {current_network}: "
            f"{', '.join(VENT_NETWORKS[current_network])})."
        )
    if destination == player.location:
        return False, "You are already at that vent destination."
    return True, ""


# ---------------------------------------------------------------------------
# Resolution helpers (called by engine.py in strict order)
# ---------------------------------------------------------------------------

def apply_kill(killer: PlayerState, victim: PlayerState, state: GameState) -> None:
    """Convert victim to ghost, drop body, cancel in-progress task, apply cooldown."""
    victim.alive = False
    victim.role = "ghost"
    victim.skip_next_turn = False

    # Cancel in-progress task
    for t in victim.tasks:
        if t.in_progress:
            t.in_progress = False

    # Drop body at kill location
    state.bodies[victim.location] = victim.color

    # Kill cooldown: 3 turns
    killer.kill_cooldown = 3

    state.event_queue.put({
        "type": "kill",
        "color": killer.color,
        "victim": victim.color,
        "location": victim.location,
    })


def apply_vent(player: PlayerState, destination: str, state: GameState) -> None:
    """Teleport impostor through vent; detect witnesses."""
    old_location = player.location
    player.location = destination

    state.event_queue.put({"type": "vent", "color": player.color, "to": destination})

    # Witness detection: any crewmate who moves INTO destination this same turn
    # is handled in engine.py after moves resolve. We flag the vent destination
    # so engine.py can check it.
    if not hasattr(state, "_vent_arrivals"):
        state._vent_arrivals = {}
    state._vent_arrivals[player.color] = destination


def apply_move(player: PlayerState, destination: str, state: GameState) -> None:
    old_location = player.location
    player.location = destination
    player.movement_log.append(
        f"R{state.round}T{state.turn}: {old_location} → {destination}"
    )
    state.event_queue.put({
        "type": "move",
        "color": player.color,
        "from": old_location,
        "to": destination,
    })


def apply_stay(player: PlayerState, state: GameState) -> None:
    state.event_queue.put({
        "type": "stay",
        "color": player.color,
        "location": player.location,
    })


def apply_task_progress(player: PlayerState, task_id: str, state: GameState) -> None:
    """Begin or continue a task. Call this during TASK phase for players who submitted work_on_task."""
    task = next((t for t in player.tasks if t.task_id == task_id), None)
    if task is None or task.completed:
        return

    if task.turns_required == 1:
        # 1-turn tasks: mark in_progress now, complete at start of next turn
        task.in_progress = True
    elif task.turns_required == 2:
        if not task.in_progress:
            task.in_progress = True
            player.skip_next_turn = True
        else:
            # Second turn — complete it
            task.in_progress = False
            task.completed = True
            player.skip_next_turn = False
            _emit_task_complete(player, task, state)


def complete_pending_tasks(player: PlayerState, state: GameState) -> None:
    """Complete any 1-turn tasks that were marked in_progress last turn and the player stayed."""
    for t in player.tasks:
        if t.in_progress and t.turns_required == 1 and t.location == player.location:
            t.in_progress = False
            t.completed = True
            _emit_task_complete(player, t, state)


def _emit_task_complete(player: PlayerState, task, state: GameState) -> None:
    state.event_queue.put({
        "type": "task_complete",
        "color": player.color,
        "task": task.name,
        "location": task.location,
    })


def compute_task_pct(state: GameState) -> float:
    total = 0
    done = 0
    for p in state.players.values():
        for t in p.tasks:
            total += 1
            if t.completed:
                done += 1
    if total == 0:
        return 1.0
    return done / total


def apply_eject(color: str, state: GameState) -> None:
    player = state.players.get(color)
    if player is None:
        return
    player.alive = False
    # Impostors don't become ghosts
    if player.role != "impostor":
        player.role = "ghost"
    else:
        player.role = "ejected"
    state.event_queue.put({"type": "ejected", "color": color})
