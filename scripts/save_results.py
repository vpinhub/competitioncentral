#!/usr/bin/env python3
"""
Fetch competition results from the VPC API and save them as JSON.
Usage: python scripts/save_results.py [ttd|swl]

Replicates the processTournament / exportTournamentData logic from the
throwdown.html and special_when_lit.html pages so results are identical
to what a browser would download via ?savejson.
"""

import sys
import json
import re
import random
import datetime
import os
import requests
from zoneinfo import ZoneInfo

CONFIGS = {
    "ttd": {
        "name": "Thursday_Throwdown",
        "room_id": "700",
        # Python weekday(): 0=Mon … 3=Thu … 6=Sun
        "cutoff_weekday": 3,
        "cutoff_hour": 14,
    },
    "swl": {
        "name": "Special_When_Lit",
        "room_id": "1011",
        "cutoff_weekday": 6,
        "cutoff_hour": 14,
    },
}

VPC_API  = "https://virtualpinballchat.com/vpc/api/v1/iscored?roomId={room_id}"
VPS_DB   = "https://raw.githubusercontent.com/VirtualPinballSpreadsheet/vps-db/main/db/vpsdb.json"
JSON_DIR = "json"
LIST_JSON = os.path.join(JSON_DIR, "list.json")
EASTERN  = ZoneInfo("America/New_York")


def calculate_period(cutoff_weekday: int, cutoff_hour: int) -> str:
    """Return 'M/D/YYYY - M/D/YYYY' period string matching the JS calculateXXXPeriod functions."""
    now = datetime.datetime.now(EASTERN)
    days_to_add = (cutoff_weekday - now.weekday() + 7) % 7
    end = now.replace(hour=cutoff_hour, minute=0, second=0, microsecond=0)
    end += datetime.timedelta(days=days_to_add)
    if days_to_add == 0 and now.hour >= cutoff_hour:
        end += datetime.timedelta(days=7)
    start = end - datetime.timedelta(days=7)
    fmt = lambda d: f"{d.month}/{d.day}/{d.year}"
    return f"{fmt(start)} - {fmt(end)}"


def process_tournament(data: list) -> tuple:
    """
    Replicate JS processTournament().
    Returns (current_results, awards, tournament_game).
    """
    # Find first game whose JSON contains 'game=', else use data[0]
    tournament_game = next(
        (g for g in data if "game=" in json.dumps(g)), data[0]
    )

    player_stats: dict = {}
    pioneer = {"name": "N/A", "date": float("inf")}

    for s in tournament_game.get("scores", []):
        name = s.get("name", "")
        try:
            val = int(s.get("score", 0))
        except (ValueError, TypeError):
            val = 0

        if name.lower() == "init" and val == 0:
            continue

        raw_date = s.get("date_added") or s.get("date") or s.get("timestamp")
        if raw_date:
            try:
                ts_ms = (
                    datetime.datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
                    .timestamp()
                    * 1000
                )
            except Exception:
                ts_ms = datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000
        else:
            ts_ms = datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000

        if ts_ms < pioneer["date"]:
            pioneer = {"name": name, "date": ts_ms}

        if name not in player_stats:
            player_stats[name] = {
                "name": name,
                "scores": [],
                "rawEntries": [],
                "high": 0,
                "low": float("inf"),
                "total": 0,
            }
        p = player_stats[name]
        p["scores"].append(val)
        p["total"] += val
        p["rawEntries"].append({"val": val, "time": ts_ms})
        if val > p["high"]:
            p["high"] = val
        if val < p["low"]:
            p["low"] = val

    player_list = []
    for p in player_stats.values():
        count = len(p["scores"])
        p["avg"] = p["total"] / count if count else 0
        p["rawEntries"].sort(key=lambda e: e["time"])
        p["comebackGrowth"] = (
            p["rawEntries"][-1]["val"] - p["rawEntries"][0]["val"]
            if len(p["rawEntries"]) > 1
            else 0
        )
        p["improvementGap"] = p["high"] - (p["low"] if p["low"] != float("inf") else p["high"])
        player_list.append(p)

    current_results = sorted(player_list, key=lambda p: p["high"], reverse=True)

    shooter   = max(player_list, key=lambda p: p["avg"],          default=None)
    grinder   = max(player_list, key=lambda p: len(p["scores"]),  default=None)
    burns     = random.choice(player_list) if player_list else None

    improved_list = sorted(player_list, key=lambda p: p["improvementGap"], reverse=True)
    comeback_list = sorted(player_list, key=lambda p: p["comebackGrowth"],  reverse=True)
    improved  = improved_list[0] if improved_list else None
    comeback  = comeback_list[0] if comeback_list else None

    if improved and comeback and improved["name"] == comeback["name"] and len(comeback_list) > 1:
        comeback = comeback_list[1]

    wooden = None
    if len(current_results) > 2:
        candidates = [p for p in current_results[1:-1] if p["improvementGap"] > 0]
        if candidates:
            wooden = candidates[-1]

    billionaire = next((p for p in current_results if p["high"] >= 1_000_000_000), None)
    nice_award  = next((p for p in current_results if str(p["high"]).startswith("69")), None)

    pir = None
    closest_margin = 5.0
    for i in range(1, len(current_results)):
        ahead = current_results[i - 1]
        curr  = current_results[i]
        if ahead["high"] > 0:
            margin = ((ahead["high"] - curr["high"]) / ahead["high"]) * 100
            if margin <= 5.0 and margin < closest_margin:
                closest_margin = margin
                pir = {"name": curr["name"], "detail": f"Closest to {ahead['name']}"}

    awards = {
        "winner":              current_results[0]["name"] if current_results else None,
        "fast_draw":           pioneer["name"],
        "fast_draw_detail":    "First Entry",
        "sharpshooter":        shooter["name"]  if shooter  else None,
        "sharpshooter_detail": "Top Average",
        "most_improved":       improved["name"] if improved else None,
        "most_improved_detail": f"Gap: +{improved['improvementGap']:,}" if improved else None,
        "comeback_kid":        comeback["name"] if comeback else None,
        "comeback_kid_detail": f"Gain: +{comeback['comebackGrowth']:,}" if comeback else None,
        "most_played":         grinder["name"]  if grinder  else None,
        "most_played_detail":  f"{len(grinder['scores'])} Games" if grinder else None,
        "burns_award":         burns["name"]    if burns    else None,
        "burns_award_detail":  "Excellent!",
        "wooden_spoon":        wooden["name"]   if wooden   else None,
        "wooden_spoon_detail": "I'm a lumberjack!",
        "price_is_right":      pir["name"]      if pir      else None,
        "price_is_right_detail": pir["detail"]  if pir      else None,
        "billionaire":         billionaire["name"] if billionaire else None,
        "billionaire_detail":  "Score > 1,000,000,000",
        "nice_award":          nice_award["name"] if nice_award else None,
        "nice_award_detail":   "Nice!",
    }

    return current_results, awards, tournament_game


def get_table_name(tournament_game: dict, vps_db: list) -> str:
    """Extract display name from VPS DB using the game= tag in the iScored room JSON."""
    tag = re.search(
        r"game=([a-zA-Z0-9\-_]+)[^#]*#([a-zA-Z0-9\-_]+)",
        json.dumps(tournament_game),
    )
    if tag:
        game_id = tag.group(1)
        table = next((t for t in vps_db if t.get("id") == game_id), None)
        if table:
            return table.get("name", tournament_game.get("longName", "Unknown"))
    return tournament_game.get("longName", "Unknown")


def update_list_json(filename: str) -> None:
    """Append the new file to list.json if not already present."""
    existing = []
    if os.path.exists(LIST_JSON):
        with open(LIST_JSON) as f:
            existing = json.load(f)

    if any(e["name"] == filename for e in existing):
        print(f"list.json already contains {filename}")
        return

    existing.append({"name": filename, "path": f"json/{filename}"})
    with open(LIST_JSON, "w") as f:
        json.dump(existing, f, indent=4)
    print(f"Updated list.json with {filename}")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in CONFIGS:
        print("Usage: save_results.py [ttd|swl]")
        sys.exit(1)

    key = sys.argv[1]
    cfg = CONFIGS[key]

    print(f"Fetching {cfg['name']} results (room {cfg['room_id']})…")
    score_data = requests.get(
        VPC_API.format(room_id=cfg["room_id"]), timeout=30
    ).json()

    print("Fetching VPS database…")
    vps_db = requests.get(VPS_DB, timeout=60).json()

    results, awards, tournament_game = process_tournament(score_data)
    table_name = get_table_name(tournament_game, vps_db)
    period     = calculate_period(cfg["cutoff_weekday"], cfg["cutoff_hour"])

    safe_table = re.sub(r"[^a-zA-Z0-9]", "_", table_name)
    safe_table = re.sub(r"_+", "_", safe_table).strip("_")
    date_str   = datetime.datetime.now(EASTERN).strftime("%Y-%m-%d")
    filename   = f"{cfg['name']}_{date_str}_{safe_table}.json"

    export = {
        "competition":   cfg["name"],
        "date_exported": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "period":        period,
        "table":         table_name,
        "awards":        awards,
        "results":       results,
    }

    os.makedirs(JSON_DIR, exist_ok=True)
    out_path = os.path.join(JSON_DIR, filename)
    with open(out_path, "w") as f:
        json.dump(export, f, indent=4)
    print(f"Saved {out_path}")

    update_list_json(filename)


if __name__ == "__main__":
    main()
