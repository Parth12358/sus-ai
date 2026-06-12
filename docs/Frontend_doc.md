# Frontend Documentation

## Overview

The frontend is `frontend/renderer.py` (1214 lines) using **pygame**. It manages its own internal screen state (`"menu"` | `"lobby"` | `"settings"`) for pre-game navigation, and renders the live game view when `game_state.phase` enters `"movement"`, `"meeting"`, `"voting"`, or `"ended"`.

## Files

| File | Purpose |
|---|---|
| `frontend/renderer.py` | All rendering, menus, lobby, settings, game view, event handling |
| `assets/bg.jpg` | Background image (fallback to starfield) |
| `main.py` | Entry point — wires renderer + engine together with asyncio |
| `settings.json` | Persisted settings (API key, model, resolution, fps, mock mode) |

---

## Screen Flow

```
Main Menu ──Start──> Lobby ──Start Game──> Game View (engine runs)
    │                    │
    └──Settings──> Settings
```

- Menu, Lobby, and Settings are managed by the renderer's internal `_screen` variable
- Game View is triggered automatically when `game_state.phase != "pregame"`
- `main.py` calls `setup_game()` + `asyncio.create_task(run_game())` on Start Game

---

## renderer.py Public API

### `init_display(width=1200, height=800, title="sus-ai") -> pygame.Surface`

Creates window, loads assets and `settings.json`, initializes stars.

### `render(screen, game_state) -> None`

Branches rendering:
- `game_state.phase in ("movement","meeting","voting","ended")` → game view
- `_screen == "menu"` → main menu
- `_screen == "lobby"` → lobby
- `_screen == "settings"` → settings form

Per-frame: updates starfield, drains event queue into `_event_log`.

### `handle_events(event, game_state) -> str | None`

Returns `"quit"` (menu quit / game over Q key) or `"start_game"` (lobby Start Game). During gameplay, Space/P toggles `game_state.paused`.

### `get_lobby_config() -> dict | None`

Returns lobby config when on lobby screen.

### `is_mock_mode() -> bool`

Returns `_settings["mock_mode"]`.

---

## Game View

Rendered when `game_state.phase` is `"movement"`, `"meeting"`, `"voting"`, or `"ended"`.

### Map (left 900px)

- Lines between adjacent rooms (from `MAP` adjacency graph)
- Room nodes: circles with labels (hallways smaller than rooms)
- Rooms with bodies get a red-tinted node
- Body X marks in the victim's color at the death location
- Players as colored circles offset around their room node (handles crowding)
  - Alive: full color + white border, impostors have a small red dot
  - Ghost: dimmed color, smaller size
  - Name label above each player

### HUD Sidebar (right 300px)

- Round/Turn counter, phase label
- Task completion progress bar (cyan fill)
- Player list: colored dot, status ([I]=impostor, [G]=ghost, [X]=ejected), short location
- Recent events: filtered to show kills, bodies, meetings, ejections, vents

### Meeting Overlay (`phase == "meeting"`)

- Dark overlay with discussion log (statements + rebuttals)
- Auto-wraps long text, scrolls if needed

### Voting Overlay (`phase == "voting"`)

- Dark overlay with vote results
- Shows who voted for whom, tally bars, ejection result

### Game Over (`phase == "ended"`)

- Dark overlay: "CREWMATES WIN!" (green) or "IMPOSTORS WIN!" (red)
- Final player status, round/turn/task stats
- Press Q to quit

### Controls during gameplay

| Key | Action |
|---|---|
| Space / P | Pause / Resume |
| Q (game over) | Quit |

---

## Background System

`assets/bg.jpg` if present (scaled cover, darkened overlay). Falls back to animated starfield (220 stars, 12% cyan-tinted, drifting).

---

## Changelog

| Date | Change |
|---|---|
| 2026-06-12 | Initial — main menu with Start/Settings/Quit, starfield + bg.jpg |
| 2026-06-12 | Added lobby screen |
| 2026-06-12 | Added settings screen with persistence |
| 2026-06-12 | Added game view — map rendering, player display, HUD, meeting/vote/game-over overlays, event log, pause toggle |
