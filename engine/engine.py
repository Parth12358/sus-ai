"""Turn loop, resolution order, win checks."""

import asyncio
import random

from engine.game_state import GameState, PlayerState, TaskState
from engine.actions import (
    apply_eject,
    apply_kill,
    apply_move,
    apply_stay,
    apply_task_progress,
    apply_vent,
    complete_pending_tasks,
    compute_task_pct,
    validate_action,
)
from engine.llm import (
    get_meeting_statement,
    get_player_action,
    get_rebuttal,
    get_vote,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _living_players(state: GameState) -> list[PlayerState]:
    return [p for p in state.players.values() if p.alive]


def _living_crewmates(state: GameState) -> list[PlayerState]:
    return [p for p in state.players.values() if p.alive and p.role == "crewmate"]


def _living_impostors(state: GameState) -> list[PlayerState]:
    return [p for p in state.players.values() if p.alive and p.role == "impostor"]


def _ghosts(state: GameState) -> list[PlayerState]:
    return [p for p in state.players.values() if p.role == "ghost"]


def _snapshot_locations(state: GameState) -> dict[str, str]:
    return {c: p.location for c, p in state.players.items() if p.alive or p.role == "ghost"}


def _build_room_events(
    state: GameState,
    prev_locations: dict[str, str],
    actions: dict[str, dict],
) -> None:
    """Populate state._room_events[color] for the upcoming turn context."""
    state._room_events = {}
    for observer_color, observer in state.players.items():
        if not (observer.alive or observer.role == "ghost"):
            continue
        events = []
        for actor_color, actor in state.players.items():
            if actor_color == observer_color:
                continue
            # Ghosts are invisible to living players
            if actor.role == "ghost" and (observer.alive and observer.role != "ghost"):
                continue
            prev = prev_locations.get(actor_color)
            curr = actor.location
            if prev is None:
                continue
            if curr == observer.location and prev != observer.location:
                events.append(f"{actor_color.upper()} arrived from {prev}")
            elif prev == observer.location and curr != observer.location:
                events.append(f"{actor_color.upper()} left to {curr}")
            elif curr == observer.location and prev == observer.location:
                act = actions.get(actor_color, {})
                if act.get("action") == "stay":
                    events.append(f"{actor_color.upper()} stayed in {curr}")
        state._room_events[observer_color] = events


# ---------------------------------------------------------------------------
# Re-prompt loop for invalid kill targets
# ---------------------------------------------------------------------------

async def _get_valid_kill_action(state: GameState, player: PlayerState) -> dict:
    action = await get_player_action(state, player)
    if action.get("action") != "kill":
        return action
    ok, err = validate_action(player, action, state)
    if ok:
        return action
    # Re-prompt once with explicit error
    error_ctx = f"INVALID ACTION: {err}\nPlease submit a valid action."
    action = await get_player_action(state, player, extra_context=error_ctx)
    ok2, err2 = validate_action(player, action, state)
    if not ok2:
        # Assign stay as fallback
        return {"action": "stay", "target": None, "reasoning": f"forced stay: {err2}"}
    return action


# ---------------------------------------------------------------------------
# Main turn loop
# ---------------------------------------------------------------------------

async def run_turn(state: GameState) -> None:
    state.turn += 1

    # Save last turn's occupancy for impostor vent context
    state._last_turn_occupancy = _snapshot_locations(state)

    # Clear vent arrival flags
    state._vent_arrivals = {}

    # Complete any 1-turn in-progress tasks from last turn
    for p in list(state.players.values()):
        if p.alive or p.role == "ghost":
            complete_pending_tasks(p, state)

    # Collect actions from all living players and ghosts (skip players on 2-turn auto-skip)
    pollable = [
        p for p in state.players.values()
        if (p.alive or p.role == "ghost") and not p.skip_next_turn
    ]
    # Players on skip get their turn auto-continued (2-turn task second turn handled in task phase)
    skipped = [
        p for p in state.players.values()
        if (p.alive or p.role == "ghost") and p.skip_next_turn
    ]
    for p in skipped:
        p.skip_next_turn = False

    tasks = [get_player_action(state, p) for p in pollable]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    actions: dict[str, dict] = {}
    for player, result in zip(pollable, results):
        if isinstance(result, Exception):
            actions[player.color] = {"action": "stay", "target": None, "reasoning": str(result)}
        else:
            actions[player.color] = result

    # Mark skipped players' actions
    for p in skipped:
        actions[p.color] = {"action": "_auto_task", "target": None}

    prev_locations = state._last_turn_occupancy.copy()

    # -----------------------------------------------------------------------
    # Resolution Step 1: KILLS
    # -----------------------------------------------------------------------
    kill_actions = {
        c: a for c, a in actions.items()
        if a.get("action") == "kill"
        and state.players[c].alive
        and state.players[c].role == "impostor"
    }

    # Validate kills; re-prompt for bad targets inline
    validated_kills: dict[str, dict] = {}
    for color, action in kill_actions.items():
        player = state.players[color]
        ok, err = validate_action(player, action, state)
        if not ok:
            error_ctx = f"INVALID ACTION: {err}\nPlease submit a valid action."
            action = await get_player_action(state, player, extra_context=error_ctx)
            ok2, _ = validate_action(player, action, state)
            if ok2 and action.get("action") == "kill":
                validated_kills[color] = action
            else:
                actions[color] = action  # may have changed to move/stay
        else:
            validated_kills[color] = action

    # Group kills by victim — if two impostors target the same crewmate, pick one randomly
    victims_targeted: dict[str, list[str]] = {}
    for killer_color, kill_action in validated_kills.items():
        victim_color = kill_action["target"]
        victims_targeted.setdefault(victim_color, []).append(killer_color)

    for victim_color, killer_colors in victims_targeted.items():
        winner_color = random.choice(killer_colors)
        killer = state.players[winner_color]
        victim = state.players.get(victim_color)
        if victim and victim.alive and victim.role not in ("impostor", "ghost"):
            apply_kill(killer, victim, state)
            # Cooldown for all impostors who attempted this kill
            for kc in killer_colors:
                state.players[kc].kill_cooldown = 3

    # Discard the victim's action if they were killed
    killed_this_turn = {
        c for c, p in state.players.items()
        if not p.alive and c in actions and prev_locations.get(c) is not None
        and state.bodies.get(p.location) == p.color
    }

    # -----------------------------------------------------------------------
    # Resolution Step 2: VENTS
    # -----------------------------------------------------------------------
    for color, action in list(actions.items()):
        if action.get("action") == "vent" and color not in killed_this_turn:
            player = state.players[color]
            if player.alive and player.role == "impostor":
                dest = action.get("target", "")
                ok, err = validate_action(player, action, state)
                if ok:
                    apply_vent(player, dest, state)

    # -----------------------------------------------------------------------
    # Resolution Step 3: MOVES (including post-kill impostor moves)
    # -----------------------------------------------------------------------
    for color, action in actions.items():
        if color in killed_this_turn:
            continue
        player = state.players[color]
        if not (player.alive or player.role == "ghost"):
            continue

        act = action.get("action")
        dest = action.get("target")

        # Impostor post-kill move — handled in the dedicated block below
        if color in validated_kills:
            continue

        if act == "move":
            ok, err = validate_action(player, action, state)
            if ok:
                apply_move(player, dest, state)
            else:
                # Re-prompt once, then stay
                error_ctx = f"INVALID MOVE: {err}"
                new_action = await get_player_action(state, player, extra_context=error_ctx)
                if new_action.get("action") == "move":
                    ok2, _ = validate_action(player, new_action, state)
                    if ok2:
                        apply_move(player, new_action["target"], state)
                        actions[color] = new_action
                        continue
                apply_stay(player, state)
                actions[color] = {"action": "stay", "target": None}
        elif act == "stay" or act == "_auto_task":
            apply_stay(player, state)

    # Witness detection for vents
    for venter_color, dest in state._vent_arrivals.items():
        for color, p in state.players.items():
            if color == venter_color:
                continue
            if p.alive and p.role != "ghost" and p.location == dest:
                state.event_queue.put({
                    "type": "vent_spotted",
                    "color": venter_color,
                    "witness": color,
                    "location": dest,
                })

    # Post-kill impostor move (fix: handle more robustly)
    for color, kill_action in validated_kills.items():
        player = state.players[color]
        if not player.alive:
            continue
        move_after = kill_action.get("move_after_kill")
        if move_after:
            from config import MAP as CMAP
            if move_after in CMAP.get(player.location, []):
                apply_move(player, move_after, state)

    # -----------------------------------------------------------------------
    # Resolution Step 4: TASKS
    # -----------------------------------------------------------------------
    for color, action in actions.items():
        if color in killed_this_turn:
            continue
        player = state.players[color]
        if not (player.alive or player.role == "ghost"):
            continue
        act = action.get("action")
        if act == "work_on_task":
            task_id = action.get("target", "")
            ok, _ = validate_action(player, action, state)
            if ok:
                apply_task_progress(player, task_id, state)
        elif act == "_auto_task":
            # 2-turn task second half
            in_prog = next((t for t in player.tasks if t.in_progress), None)
            if in_prog and in_prog.location == player.location:
                apply_task_progress(player, in_prog.task_id, state)

    state.task_pct = compute_task_pct(state)

    # -----------------------------------------------------------------------
    # Resolution Step 5: MEETING TRIGGERS
    # -----------------------------------------------------------------------
    meeting_trigger = None
    report_candidates = []
    emergency_candidates = []

    for color, action in actions.items():
        if color in killed_this_turn:
            continue
        player = state.players[color]
        if not player.alive:
            continue
        act = action.get("action")
        if act == "report_body":
            ok, _ = validate_action(player, action, state)
            if ok:
                report_candidates.append(color)
        elif act == "call_meeting":
            ok, _ = validate_action(player, action, state)
            if ok:
                emergency_candidates.append(color)

    if report_candidates:
        caller_color = random.choice(report_candidates)
        victim_color = state.bodies.get(state.players[caller_color].location, "unknown")
        meeting_trigger = ("body", caller_color, victim_color)
    elif emergency_candidates:
        caller_color = random.choice(emergency_candidates)
        state.players[caller_color]._used_emergency_meeting = True
        meeting_trigger = ("emergency", caller_color, None)

    # Build room events for next turn context
    _build_room_events(state, prev_locations, actions)

    # Tick kill cooldowns (for impostors who did NOT kill this turn)
    for p in _living_impostors(state):
        if p.color not in validated_kills and p.kill_cooldown > 0:
            p.kill_cooldown -= 1

    # -----------------------------------------------------------------------
    # Resolution Step 6: WIN CHECK
    # -----------------------------------------------------------------------
    winner = check_win_conditions(state)
    if winner:
        state.winner = winner
        state.phase = "ended"
        state.event_queue.put({"type": "game_over", "winner": winner})
        return

    # Fire meeting if triggered
    if meeting_trigger:
        kind, caller_color, victim_color = meeting_trigger
        if kind == "body":
            state.event_queue.put({
                "type": "body_found",
                "reporter": caller_color,
                "victim": victim_color,
                "location": state.players[caller_color].location,
            })
        state.event_queue.put({
            "type": "meeting_called",
            "caller": caller_color,
            "reason": "body" if kind == "body" else "emergency",
        })
        await run_meeting_phase(state, caller_color, kind, victim_color)

        winner = check_win_conditions(state)
        if winner:
            state.winner = winner
            state.phase = "ended"
            state.event_queue.put({"type": "game_over", "winner": winner})
            return

        _start_new_round(state)


def _start_new_round(state: GameState) -> None:
    state.round += 1
    state.turn = 0
    state.meeting_log = []
    # All living players (and ghosts) move to cafeteria
    for p in state.players.values():
        if p.alive or p.role == "ghost":
            p.location = "cafeteria"
    state.phase = "movement"


# ---------------------------------------------------------------------------
# Meeting phase
# ---------------------------------------------------------------------------

async def run_meeting_phase(
    state: GameState,
    caller_color: str,
    kind: str,
    victim_color: str | None,
) -> None:
    state.phase = "meeting"
    state.meeting_log = []

    living = [p for p in state.players.values() if p.alive]
    if not living:
        return

    if kind == "body":
        trigger_text = f"{caller_color.upper()} found the body of {(victim_color or '?').upper()}."
    else:
        trigger_text = f"{caller_color.upper()} called an emergency meeting."

    # Opening statements — caller goes first, then randomized order
    order = [p for p in living if p.color != caller_color]
    random.shuffle(order)
    order = [state.players[caller_color]] + order

    # Gather all scratchpad updates + opening statements in parallel
    statement_tasks = [get_meeting_statement(state, p, trigger_text) for p in order]
    statement_results = await asyncio.gather(*statement_tasks, return_exceptions=True)

    mentioned: dict[str, list[str]] = {}  # mentioned_color -> [mentioner_colors]

    for player, result in zip(order, statement_results):
        if isinstance(result, Exception):
            result = {"scratchpad": player.scratchpad, "statement": "(no statement)"}
        player.scratchpad = result.get("scratchpad", player.scratchpad)
        statement = result.get("statement", "(no statement)")
        entry = {"type": "statement", "color": player.color, "text": statement}
        state.meeting_log.append(entry)

        # Detect mentions of other players
        for other in living:
            if other.color != player.color and other.color in statement.lower():
                mentioned.setdefault(other.color, []).append(player.color)

    # Rebuttals — players who were mentioned may respond (max 2 per player per meeting)
    rebuttal_counts: dict[str, int] = {p.color: 0 for p in living}

    for mentioned_color in mentioned:
        player = state.players.get(mentioned_color)
        if player is None or not player.alive:
            continue
        if rebuttal_counts[mentioned_color] >= 2:
            continue

        used = rebuttal_counts[mentioned_color]
        result = await get_rebuttal(state, player, used)
        rebuttal_text = result.get("rebuttal")
        if rebuttal_text:
            rebuttal_counts[mentioned_color] += 1
            state.meeting_log.append({
                "type": "rebuttal",
                "color": player.color,
                "text": rebuttal_text,
            })

    # Voting phase
    state.phase = "voting"
    vote_tasks = [get_vote(state, p) for p in living]
    vote_results = await asyncio.gather(*vote_tasks, return_exceptions=True)

    votes: dict[str, str] = {}
    for player, result in zip(living, vote_results):
        if isinstance(result, Exception):
            votes[player.color] = "skip"
        else:
            raw_vote = result.get("vote", "skip")
            votes[player.color] = raw_vote

    # Tally votes
    tally: dict[str, int] = {}
    for voter_color, voted_for in votes.items():
        if voted_for == "skip":
            continue
        tally[voted_for] = tally.get(voted_for, 0) + 1

    total_votes_cast = sum(tally.values())
    ejected = None
    if total_votes_cast > 0:
        top_color = max(tally, key=lambda c: tally[c])
        top_votes = tally[top_color]
        if top_votes > total_votes_cast / 2:
            ejected = top_color

    state.vote_results = {
        "votes": votes,
        "tally": tally,
        "ejected": ejected,
    }

    if ejected:
        apply_eject(ejected, state)

    state.phase = "movement"


# ---------------------------------------------------------------------------
# Win conditions
# ---------------------------------------------------------------------------

def check_win_conditions(state: GameState) -> str | None:
    living_crew = _living_crewmates(state)
    living_imp = _living_impostors(state)

    # Crewmates win by ejecting all impostors
    if len(living_imp) == 0:
        # Check there are actually impostors in the game (avoid false win at pregame)
        has_impostors = any(
            p.role in ("impostor", "ejected")
            for p in state.players.values()
        )
        if has_impostors:
            return "crewmates"

    # Impostors win when they match or outnumber living crewmates
    if len(living_imp) >= len(living_crew) and len(living_imp) > 0:
        return "impostors"

    # Crewmates win by task completion
    if state.task_pct >= 1.0:
        total_tasks = sum(len(p.tasks) for p in state.players.values())
        if total_tasks > 0:
            return "crewmates"

    return None


# ---------------------------------------------------------------------------
# Pregame setup
# ---------------------------------------------------------------------------

def setup_game(state: GameState, roster: list[dict], task_count: int = 4) -> None:
    """Populate GameState from roster. Call before starting the turn loop."""
    from config import TASKS

    common_tasks = [t for t in TASKS if t["type"] == "common"]
    short_tasks = [t for t in TASKS if t["type"] == "short"]

    # Determine impostor colors from roster (role key), else assign randomly
    impostor_colors = [r["color"] for r in roster if r.get("role") == "impostor"]
    if not impostor_colors:
        # Default: 1 impostor for <=5 players, 2 for 6-8
        n_imp = 1 if len(roster) <= 5 else 2
        chosen = random.sample([r["color"] for r in roster], n_imp)
        impostor_colors = chosen

    for entry in roster:
        color = entry["color"]
        model = entry["model"]
        role = "impostor" if color in impostor_colors else "crewmate"

        player_tasks: list[TaskState] = []
        if role == "crewmate":
            # Assign all common tasks
            for t in common_tasks:
                player_tasks.append(TaskState(
                    task_id=t["id"], name=t["name"], location=t["location"],
                    turns_required=t["turns"],
                ))
            # Assign random short tasks
            chosen_short = random.sample(short_tasks, min(task_count, len(short_tasks)))
            for t in chosen_short:
                player_tasks.append(TaskState(
                    task_id=t["id"], name=t["name"], location=t["location"],
                    turns_required=t["turns"],
                ))

        player = PlayerState(
            color=color,
            model=model,
            role=role,
            location="cafeteria",
            tasks=player_tasks,
            kill_cooldown=3 if role == "impostor" else 0,
        )
        state.players[color] = player

    state.round = 1
    state.turn = 0
    state.phase = "movement"
    state.task_pct = compute_task_pct(state)
    state._last_turn_occupancy = {c: "cafeteria" for c in state.players}
    state._room_events = {}


# ---------------------------------------------------------------------------
# Full game loop
# ---------------------------------------------------------------------------

async def run_game(state: GameState) -> None:
    """Drive the full game. Call after setup_game()."""
    while state.phase != "ended":
        if state.paused:
            await asyncio.sleep(0.1)
            continue
        await run_turn(state)
        await asyncio.sleep(0)  # yield to pygame event loop
