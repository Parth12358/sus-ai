"""OpenRouter API calls, prompt building, response parsing."""

import json
import os
import random
import re

import httpx

from config import MAP, VENT_NETWORKS
from engine.game_state import GameState, PlayerState
from engine.prompts import (
    MEETING_REBUTTAL_PROMPT,
    MEETING_SCRATCHPAD_PROMPT,
    MEETING_VOTE_PROMPT,
    build_crewmate_prompt,
    build_ghost_prompt,
    build_impostor_prompt,
)

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_MOCK = False


def set_mock(enabled: bool) -> None:
    global _MOCK
    _MOCK = enabled


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    return key


def _system_prompt(player: PlayerState, state: GameState) -> str:
    if player.role == "ghost":
        return build_ghost_prompt(player.color)
    if player.role == "impostor":
        fellows = [
            c for c, p in state.players.items()
            if p.role == "impostor" and c != player.color
        ]
        return build_impostor_prompt(player.color, fellows)
    return build_crewmate_prompt(player.color)


def build_turn_context(state: GameState, player: PlayerState) -> str:
    lines: list[str] = []
    lines.append(f"=== TURN {state.turn} — ROUND {state.round} ===")
    lines.append(f"Your location: {player.location}")
    lines.append(f"Global task completion: {state.task_pct * 100:.0f}%")

    if player.role == "impostor":
        if player.kill_cooldown > 0:
            lines.append(f"Kill cooldown: {player.kill_cooldown} turns remaining")
        else:
            lines.append("Kill cooldown: READY")

    # Bodies in current room
    bodies_here = [color for loc, color in state.bodies.items() if loc == player.location]
    if bodies_here:
        body_list = ", ".join(f"{c} body at {player.location}" for c in bodies_here)
        lines.append(f"\nBODIES IN YOUR ROOM: {body_list} — report_body is available")
    else:
        lines.append("\nBODIES IN YOUR ROOM: none")

    # Room events (stored on state for the current turn)
    room_events = getattr(state, "_room_events", {}).get(player.color, [])
    if room_events:
        lines.append("\nROOM EVENTS THIS TURN:")
        for ev in room_events:
            lines.append(f"  - {ev}")
    else:
        lines.append("\nROOM EVENTS THIS TURN: no movement events")

    # Tasks (crewmates and ghosts)
    if player.role in ("crewmate", "ghost") and player.tasks:
        lines.append("\nYOUR TASKS:")
        for t in player.tasks:
            if t.completed:
                status = "done"
            elif t.in_progress:
                status = "in_progress"
            else:
                status = "pending"
            lines.append(f"  - {t.name} @ {t.location} [{t.task_id}] — {status}")

    # Vent network occupancy (impostors — last turn snapshot)
    if player.role == "impostor":
        player_network = None
        for net_id, nodes in VENT_NETWORKS.items():
            if player.location in nodes:
                player_network = net_id
                break
        if player_network is not None:
            last_occ = getattr(state, "_last_turn_occupancy", {})
            nodes = VENT_NETWORKS[player_network]
            lines.append(f"\nVENT NETWORK OCCUPANCY (last turn) — Network {player_network}:")
            for node in nodes:
                occupants = [
                    c for c, loc in last_occ.items()
                    if loc == node and c != player.color
                ]
                occ_str = ", ".join(occupants) if occupants else "empty"
                lines.append(f"  {node}: {occ_str}")

    # Scratchpad
    lines.append(f"\nYOUR SCRATCHPAD (read-only this phase):\n{player.scratchpad or '(empty)'}")

    return "\n".join(lines)


def _mock_action(player: PlayerState, state: GameState) -> dict:
    from config import MAP as CMAP
    role = player.role

    if role == "ghost":
        pending = [t for t in player.tasks if not t.completed]
        if pending:
            t = pending[0]
            if player.location == t.location:
                return {"reasoning": "mock", "action": "work_on_task", "target": t.task_id}
            return {"reasoning": "mock", "action": "move", "target": t.location}
        return {"reasoning": "mock", "action": "stay", "target": None}

    if role == "impostor" and player.kill_cooldown == 0:
        targets = [
            c for c, p in state.players.items()
            if p.alive and p.role == "crewmate" and p.location == player.location
        ]
        if targets:
            victim = random.choice(targets)
            neighbors = CMAP.get(player.location, [])
            move_to = random.choice(neighbors) if neighbors else None
            return {
                "reasoning": "mock kill",
                "action": "kill",
                "target": victim,
                "move_after_kill": move_to,
            }

    neighbors = CMAP.get(player.location, [])
    if neighbors and random.random() < 0.6:
        return {"reasoning": "mock", "action": "move", "target": random.choice(neighbors)}

    pending_tasks = [
        t for t in player.tasks
        if not t.completed and not t.in_progress and t.location == player.location
    ]
    if pending_tasks and role == "crewmate":
        return {"reasoning": "mock", "action": "work_on_task", "target": pending_tasks[0].task_id}

    return {"reasoning": "mock", "action": "stay", "target": None}


def parse_response(raw: str) -> dict:
    raw = raw.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


async def _call_api(model: str, system: str, user: str) -> str:
    headers = {
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(OPENROUTER_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


async def get_player_action(
    state: GameState,
    player: PlayerState,
    extra_context: str = "",
) -> dict:
    if _MOCK:
        return _mock_action(player, state)

    system = _system_prompt(player, state)
    user = build_turn_context(state, player)
    if extra_context:
        user = extra_context + "\n\n" + user

    raw = ""
    for attempt in range(2):
        try:
            raw = await _call_api(player.model, system, user)
            result = parse_response(raw)
            return result
        except (json.JSONDecodeError, KeyError) as exc:
            if attempt == 0:
                user = f"Your last response was not valid JSON: {exc}\n\nPlease respond with valid JSON only.\n\n{user}"
            else:
                return {"reasoning": "parse failure", "action": "stay", "target": None}
        except httpx.HTTPError as exc:
            if attempt == 0:
                user = f"API error on last attempt: {exc}\n\n{user}"
            else:
                return {"reasoning": "api failure", "action": "stay", "target": None}

    return {"reasoning": "fallback", "action": "stay", "target": None}


async def get_meeting_statement(
    state: GameState,
    player: PlayerState,
    meeting_trigger: str,
) -> dict:
    if _MOCK:
        return {
            "scratchpad": player.scratchpad,
            "statement": f"I have nothing suspicious to report. [mock]",
        }

    discussion_so_far = _format_discussion(state.meeting_log)
    prompt = MEETING_SCRATCHPAD_PROMPT.format(
        meeting_trigger=meeting_trigger,
        previous_scratchpad=player.scratchpad or "(empty)",
        discussion_log=discussion_so_far or "(none yet)",
    )
    system = _system_prompt(player, state)
    for attempt in range(2):
        try:
            raw = await _call_api(player.model, system, prompt)
            return parse_response(raw)
        except (json.JSONDecodeError, KeyError, httpx.HTTPError):
            if attempt == 1:
                return {"scratchpad": player.scratchpad, "statement": "(no statement)"}
    return {"scratchpad": player.scratchpad, "statement": "(no statement)"}


async def get_rebuttal(
    state: GameState,
    player: PlayerState,
    rebuttals_used: int,
) -> dict:
    if _MOCK:
        return {"rebuttal": None}

    discussion = _format_discussion(state.meeting_log)
    prompt = MEETING_REBUTTAL_PROMPT.format(
        rebuttals_used=rebuttals_used,
        discussion_log=discussion,
    )
    system = _system_prompt(player, state)
    for attempt in range(2):
        try:
            raw = await _call_api(player.model, system, prompt)
            return parse_response(raw)
        except (json.JSONDecodeError, KeyError, httpx.HTTPError):
            if attempt == 1:
                return {"rebuttal": None}
    return {"rebuttal": None}


async def get_vote(
    state: GameState,
    player: PlayerState,
) -> dict:
    if _MOCK:
        living = [c for c, p in state.players.items() if p.alive and c != player.color]
        return {"vote": random.choice(living + ["skip"])}

    discussion = _format_discussion(state.meeting_log)
    prompt = MEETING_VOTE_PROMPT.format(full_discussion_log=discussion)
    system = _system_prompt(player, state)
    for attempt in range(2):
        try:
            raw = await _call_api(player.model, system, prompt)
            return parse_response(raw)
        except (json.JSONDecodeError, KeyError, httpx.HTTPError):
            if attempt == 1:
                return {"vote": "skip"}
    return {"vote": "skip"}


def _format_discussion(meeting_log: list[dict]) -> str:
    if not meeting_log:
        return "(none)"
    lines = []
    for entry in meeting_log:
        kind = entry.get("type", "statement")
        color = entry.get("color", "?")
        text = entry.get("text", "")
        if kind == "statement":
            lines.append(f"[{color.upper()}] {text}")
        elif kind == "rebuttal":
            lines.append(f"[{color.upper()} rebuttal] {text}")
    return "\n".join(lines)
