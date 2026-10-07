# automation_flight_board_schedule.py
#
# PURPOSE
#   Companion script for the Flight Board Card. It fills in what the Flightradar24
#   integration does not provide:
#     - the SCHEDULE of flights that are not airborne yet (route, times)
#     - GATE, TERMINAL and BAGGAGE BELT for the departure and the arrival airport
#     - LIVE POSITION from OpenSky Network (lat/lon, altitude, speed, heading,
#       vertical rate) as a second source next to Flightradar24
#   Everything is published in ONE sensor (sensor.flight_board_schedule) that the
#   card reads. The card's flight pop-up (click a flight) uses it.
#
# HOW IT WORKS
#   - Flights looked up: every flight in sensor.flightradar24_additional_tracked
#     (live or not), the optional EXTRA_FLIGHTS list below, and every flight the
#     card asks about (pyscript.flight_board_lookup, sent when you open a pop-up
#     or track a flight). Card requests expire after WATCH_MINUTES.
#   - Schedule comes from the same Flightradar24 data that the flightradar24.com
#     flight page uses. Gate, terminal and belt come from the Flightradar24 flight
#     detail view (flights in the air) and from the airport board of the airport
#     the card shows (flights that have not departed yet).
#   - OpenSky is only asked for flights that are airborne, in one request for all
#     of them, at most once per OPENSKY_REFRESH_SECONDS. When OpenSky answers
#     "too many requests" (429) the script pauses OpenSky and keeps the last position.
#   - Results are cached so Flightradar24 is asked at most once per CACHE_SECONDS.
#   - Aviationstack (optional, free plan = 100 requests a month) is asked ONLY when
#     you click a flight, to fill an empty gate, terminal or belt. See AVIATIONSTACK_*.
#
# OPENSKY ACCOUNT (optional)
#   Works without an account (about 400 requests a day, shared by IP). A free
#   OpenSky account raises that a lot: create an API client on opensky-network.org
#   (Account page) and put the client id and secret in OPENSKY_CLIENT_ID and
#   OPENSKY_CLIENT_SECRET below. If both stay empty, OpenSky is used anonymously.
#   Set OPENSKY_ENABLED = False to switch OpenSky off.
#
# NOTES
#   - Flightradar24 and OpenSky data is fetched through unofficial / rate limited
#     web APIs. When a source fails the script logs a warning, keeps the last good
#     data and sends ONE notification per NOTIFY_COOLDOWN_SECONDS.
#   - Gates are often empty until a few hours before departure; some airports
#     never publish them. Empty values are simply not shown by the card.
#   - OpenSky only knows aircraft that its receivers hear, so coverage varies. When it
#     has no (fresh) position the script falls back to Flightradar24, Aviationstack and
#     finally an estimate along the route (see POSITION_* below), so a flying aircraft always has one.
#   - PyScript sensors are not saved across a full HA restart; the startup trigger
#     rebuilds the sensor every time PyScript loads.
#   - Only the Python standard library is used (urllib, json), no extra install.

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request

# =============================================================================
# VARIABLES (all settings live here)
# =============================================================================

# Sensor created by the Flightradar24 integration that lists the tracked flights
TRACKED_SENSOR = "sensor.flightradar24_additional_tracked"

# Sensor created by this script (the card reads it)
OUT_SENSOR = "sensor.flight_board_schedule"
OUT_NAME = "Flight board schedule"
OUT_ICON = "mdi:airplane-clock"

# Extra flight numbers to always look up, even if the card did not add them.
# Example: ["AA4415", "DL1234"]
EXTRA_FLIGHTS = []

# Flights the card asks about (pop-up / tracker) are watched for this many minutes
WATCH_MINUTES = 180

# Flightradar24 flight list endpoint (same data as the flight page)
FR24_URL = "https://api.flightradar24.com/common/v1/flight/list.json?query={query}&fetchBy=flight&page=1&limit=25"
BROWSER_USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
FETCH_TIMEOUT_SECONDS = 15

# Flight detail endpoint (the flight list leaves gate, terminal and belt empty,
# the detail view of a single flight has them). Used for the chosen flight only.
FR24_DETAIL_URL = "https://data-live.flightradar24.com/clickhandler/?version=1.5&flight={flight_id}"

# Flightradar24 airport board for YOUR airport (the one the card shows). Unlike the
# flight list it carries gate, terminal and baggage belt for flights that have not
# departed yet. Two requests (departures + arrivals) per BOARD_CACHE_SECONDS.
FR24_BOARD_URL = "https://api.flightradar24.com/common/v1/airport.json?code={code}&plugin[]=schedule&plugin-setting[schedule][mode]={mode}&page=1&limit=100"
# Entity that holds the airport the card shows (Flightradar24 integration)
HOME_AIRPORT_ENTITY = "text.flightradar24_airport_track"
BOARD_CACHE_SECONDS = 600

# Gate sensor for the card's London style: gate (departures) and baggage belt
# (arrivals) of every flight on the airport board, in one small sensor.
PUBLISH_BOARD_GATES = True
GATES_SENSOR = "sensor.flight_board_gates"
GATES_NAME = "Flight board gates"
GATES_ICON = "mdi:gate"
# A board entry only matches a flight when its scheduled departure is within this many seconds
BOARD_MATCH_SECONDS = 6 * 3600

# Second gate source (optional): AeroDataBox through RapidAPI. It lists gate,
# terminal and baggage belt per flight. Subscribe to the free plan at
# https://rapidapi.com/aedbx-aedbx/api/aerodatabox and paste your key here.
# Leave the key empty to switch it off. It is only asked when Flightradar24 has no
# gate, for flights leaving or landing within ADB_WINDOW_HOURS, and at most once
# per ADB_CACHE_SECONDS per flight (the free plan has a small monthly quota).
AERODATABOX_API_KEY = ""
AERODATABOX_HOST = "aerodatabox.p.rapidapi.com"
AERODATABOX_URL = "https://aerodatabox.p.rapidapi.com/flights/number/{number}/{date}?withAircraftImage=false&withLocation=false"
ADB_WINDOW_HOURS = 8
ADB_CACHE_SECONDS = 1800

# Third gate source (optional): Aviationstack. The FREE plan only allows 100
# requests a MONTH, so it is NEVER used by the periodic rebuild. It is asked only
# when you click a flight (pyscript.flight_board_lookup from the card pop-up), at
# most once per AVS_CACHE_SECONDS per flight, and never more than AVS_MONTHLY_LIMIT
# times a month (the counter restarts when PyScript reloads, so the limit is a
# safety net; Aviationstack also refuses requests itself once your quota is used).
# It only fills gate, terminal and baggage belt that are still empty.
# Create the key at https://aviationstack.com and paste it here (do not share it).
# Leave it empty to switch it off.
AVIATIONSTACK_API_KEY = ""
AVIATIONSTACK_URL = "https://api.aviationstack.com/v1/flights"
AVS_CACHE_SECONDS = 3600
AVS_MONTHLY_LIMIT = 90

# POSITION FALLBACKS (so a flying aircraft always has a position)
# Order: OpenSky -> Flightradar24 integration position -> Flightradar24 flight
# track -> Aviationstack (only after a click) -> estimate along the route.
# An OpenSky position older than POSITION_STALE_SECONDS counts as missing.
# The estimate is a straight line between the two airports based on the times;
# it is labelled "Estimated" on the card and has no altitude or speed.
POSITION_STALE_SECONDS = 600
POSITION_ESTIMATE = True
TRAIL_CACHE_SECONDS = 120

# A flight is looked up at most once per this many seconds
CACHE_SECONDS = 900

# OpenSky Network (live position, second source)
OPENSKY_ENABLED = True
OPENSKY_CLIENT_ID = ""
OPENSKY_CLIENT_SECRET = ""
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"
OPENSKY_TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
# Seconds between OpenSky requests. All airborne flights are asked in ONE request,
# so this is the number of seconds between requests. Anonymous use has about 400
# credits a day, so keep this at 300 or more unless you added an account.
OPENSKY_REFRESH_SECONDS = 300
# When OpenSky answers "too many requests" (HTTP 429), stop asking for this many
# seconds (OpenSky's own wait time is used when it sends one)
OPENSKY_BACKOFF_SECONDS = 1800
# When the aircraft id (icao24) is unknown, search a box this many degrees wide
# around its last known position instead
OPENSKY_BOX_DEGREES = 0.6

# How often the sensor is rebuilt (also rebuilt when the tracked sensor changes)
REFRESH_PERIOD_SECONDS = 60

# A leg that landed more than this many seconds ago is treated as finished
FINISHED_AFTER_SECONDS = 3 * 3600

# Error notifications
NOTIFY_SERVICE_NAME = "mobile_app_iphone_rg"
NOTIFY_TITLE = "Flight board schedule"
PERSISTENT_NOTIFICATION_ID = "flight_board_schedule_error"
# Minimum seconds between repeated error notifications (avoids spam)
NOTIFY_COOLDOWN_SECONDS = 3600

# Seconds a lookup request waits for a running rebuild to finish
LOOKUP_WAIT_SECONDS = 25

# Log prefix
LOG_PREFIX = "flight_board_schedule"

# Mutable module state (a dict avoids needing "global")
SCHEDULE_STATE = {
    "last_notify": 0,
    "cache": {},       # code -> {"at": ts, "leg": dict or None}
    "os_cache": {},    # code -> {"at": ts, "data": dict or None}
    "adb_cache": {},   # code -> {"at": ts, "fields": dict}
    "avs_cache": {},   # code -> {"at": ts, "fields": dict}  (filled only by a card click)
    "trail_cache": {}, # code -> {"at": ts, "data": dict or None}
    "avs_usage": {"month": "", "count": 0, "logged": False},
    "board_cache": {}, # "airport|mode" -> {"at": ts, "items": {flight number: [entries]}}
    "watch": {},       # code -> expiry timestamp (asked by the card)
    "token": {"value": "", "expires": 0},
    "os_block_until": 0,  # OpenSky said "too many requests": do not ask before this time
    "busy": False,
}


# =============================================================================
# HELPERS
# =============================================================================

def fb_sched_notify_error(message):
    # Send an error to the iPhone AND to the Home Assistant notification panel,
    # at most once per NOTIFY_COOLDOWN_SECONDS. Never raises.
    try:
        now = time.time()
        if now - SCHEDULE_STATE["last_notify"] < NOTIFY_COOLDOWN_SECONDS:
            return
        SCHEDULE_STATE["last_notify"] = now

        # Phone notification
        try:
            service.call("notify", NOTIFY_SERVICE_NAME, title=NOTIFY_TITLE, message=message)
        except Exception as e:
            log.error(f"{LOG_PREFIX}: phone notify failed: {e}")

        # Home Assistant notification
        try:
            service.call(
                "persistent_notification",
                "create",
                title=NOTIFY_TITLE,
                message=message,
                notification_id=PERSISTENT_NOTIFICATION_ID,
            )
        except Exception as e:
            log.error(f"{LOG_PREFIX}: persistent notification failed: {e}")
    except Exception as e:
        log.error(f"{LOG_PREFIX}: notify helper failed: {e}")


def fb_sched_get(data, path):
    # Safe nested lookup: path is a list of keys. Returns None if anything is missing.
    cur = data
    for key in path:
        if cur is None:
            return None
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def fb_sched_clean(value):
    # Text value or None: empty strings and "N/A" style placeholders become None
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.upper() in ("N/A", "NA", "NONE", "NULL", "-"):
        return None
    return text


def fb_sched_norm(value):
    # Upper case, letters and digits only ("aa 4415" -> "AA4415")
    out = ""
    for ch in str(value or "").upper():
        if ch.isalnum():
            out = out + ch
    return out


def fb_sched_http_json(url, headers=None, data=None):
    # Download and parse JSON. Blocking calls run in a worker thread so Home
    # Assistant is not held up. Raises on network or parse errors.
    hdrs = {"User-Agent": BROWSER_USER_AGENT, "Accept": "application/json"}
    if headers:
        for key in headers:
            hdrs[key] = headers[key]
    req = urllib.request.Request(url, data=data, headers=hdrs)
    resp = task.executor(urllib.request.urlopen, req, timeout=FETCH_TIMEOUT_SECONDS)
    raw = task.executor(resp.read)
    try:
        task.executor(resp.close)
    except Exception:
        pass
    return json.loads(raw.decode("utf-8"))


def fb_sched_leg(item):
    # Turn one Flightradar24 flight list entry into the attribute layout the card uses.
    return {
        "flight_id": fb_sched_get(item, ["identification", "id"]),
        "flight_number": fb_sched_get(item, ["identification", "number", "default"]),
        "callsign": fb_sched_get(item, ["identification", "callsign"]),
        "aircraft_registration": fb_sched_get(item, ["aircraft", "registration"]),
        "aircraft_model": fb_sched_get(item, ["aircraft", "model", "text"]),
        "aircraft_code": fb_sched_get(item, ["aircraft", "model", "code"]),
        "aircraft_hex": fb_sched_clean(fb_sched_get(item, ["aircraft", "hex"])),
        "airline": fb_sched_get(item, ["airline", "name"]),
        "airline_short": fb_sched_get(item, ["airline", "short"]),
        "airline_iata": fb_sched_get(item, ["airline", "code", "iata"]),
        "airline_icao": fb_sched_get(item, ["airline", "code", "icao"]),
        "airport_origin_name": fb_sched_get(item, ["airport", "origin", "name"]),
        "airport_origin_code_iata": fb_sched_get(item, ["airport", "origin", "code", "iata"]),
        "airport_origin_code_icao": fb_sched_get(item, ["airport", "origin", "code", "icao"]),
        "airport_origin_city": fb_sched_get(item, ["airport", "origin", "position", "region", "city"]),
        "airport_origin_latitude": fb_sched_get(item, ["airport", "origin", "position", "latitude"]),
        "airport_origin_longitude": fb_sched_get(item, ["airport", "origin", "position", "longitude"]),
        "airport_origin_gate": fb_sched_clean(fb_sched_get(item, ["airport", "origin", "info", "gate"])),
        "airport_origin_terminal": fb_sched_clean(fb_sched_get(item, ["airport", "origin", "info", "terminal"])),
        "airport_origin_baggage": fb_sched_clean(fb_sched_get(item, ["airport", "origin", "info", "baggage"])),
        "airport_destination_name": fb_sched_get(item, ["airport", "destination", "name"]),
        "airport_destination_code_iata": fb_sched_get(item, ["airport", "destination", "code", "iata"]),
        "airport_destination_code_icao": fb_sched_get(item, ["airport", "destination", "code", "icao"]),
        "airport_destination_city": fb_sched_get(item, ["airport", "destination", "position", "region", "city"]),
        "airport_destination_latitude": fb_sched_get(item, ["airport", "destination", "position", "latitude"]),
        "airport_destination_longitude": fb_sched_get(item, ["airport", "destination", "position", "longitude"]),
        "airport_destination_gate": fb_sched_clean(fb_sched_get(item, ["airport", "destination", "info", "gate"])),
        "airport_destination_terminal": fb_sched_clean(fb_sched_get(item, ["airport", "destination", "info", "terminal"])),
        "airport_destination_baggage": fb_sched_clean(fb_sched_get(item, ["airport", "destination", "info", "baggage"])),
        "time_scheduled_departure": fb_sched_get(item, ["time", "scheduled", "departure"]),
        "time_scheduled_arrival": fb_sched_get(item, ["time", "scheduled", "arrival"]),
        "time_estimated_departure": fb_sched_get(item, ["time", "estimated", "departure"]),
        "time_estimated_arrival": fb_sched_get(item, ["time", "estimated", "arrival"]),
        "time_real_departure": fb_sched_get(item, ["time", "real", "departure"]),
        "time_real_arrival": fb_sched_get(item, ["time", "real", "arrival"]),
        "status_text": fb_sched_get(item, ["status", "text"]),
        "is_live": bool(fb_sched_get(item, ["status", "live"])),
    }


def fb_sched_pick(legs, now):
    # Choose the most relevant leg: a live one first, then the nearest one that has not
    # finished, then the nearest of any. "Nearest" = scheduled departure closest to now.
    best = None
    best_rank = 9
    best_dist = 0
    for leg in legs:
        dep = leg.get("time_scheduled_departure")
        if dep is None:
            dep = leg.get("time_estimated_departure")
        if dep is None:
            continue
        arr = leg.get("time_real_arrival")
        if leg.get("is_live"):
            rank = 0
        elif arr is None and dep >= now - FINISHED_AFTER_SECONDS:
            rank = 1
        elif arr is not None and arr >= now - FINISHED_AFTER_SECONDS:
            rank = 1
        else:
            rank = 2
        dist = abs(dep - now)
        if best is None or rank < best_rank or (rank == best_rank and dist < best_dist):
            best = leg
            best_rank = rank
            best_dist = dist
    return best


def fb_sched_add_details(leg):
    # The flight list usually has no gate, terminal or belt. When a gate is missing,
    # ask the detail view of this one flight and fill them in. A failure here
    # only logs a warning: the leg is still published without gate data.
    keys = ["gate", "terminal", "baggage"]
    flight_id = leg.get("flight_id")
    if not flight_id:
        return
    # Nothing to add when both gates are already known
    if leg.get("airport_origin_gate") and leg.get("airport_destination_gate"):
        return
    try:
        payload = fb_sched_http_json(FR24_DETAIL_URL.replace("{flight_id}", str(flight_id)))
        for side in ["origin", "destination"]:
            for k in keys:
                value = fb_sched_clean(fb_sched_get(payload, ["airport", side, "info", k]))
                if value:
                    leg["airport_" + side + "_" + k] = value
    except Exception as e:
        log.warning(f"{LOG_PREFIX}: gate details for {leg.get('flight_number')} failed: {e}")


def fb_sched_board(code, mode):
    # Gate data of one airport board, cached. Returns {flight number: [entries]} where
    # an entry is {"dep": scheduled departure, "fields": gate dict}. Raises on errors.
    cache = SCHEDULE_STATE["board_cache"]
    key = code + "|" + mode
    now = time.time()
    entry = cache.get(key)
    if entry is not None and now - entry["at"] < BOARD_CACHE_SECONDS:
        return entry["items"]
    url = FR24_BOARD_URL.replace("{code}", code.lower()).replace("{mode}", mode)
    payload = fb_sched_http_json(url)
    rows = fb_sched_get(payload, ["result", "response", "airport", "pluginData", "schedule", mode, "data"]) or []
    items = {}
    for row in rows:
        try:
            fl = None
            if isinstance(row, dict):
                fl = row.get("flight") if isinstance(row.get("flight"), dict) else row
            number = fb_sched_norm(fb_sched_get(fl, ["identification", "number", "default"]))
            if not number:
                continue
            fields = {
                "airport_origin_gate": fb_sched_clean(fb_sched_get(fl, ["airport", "origin", "info", "gate"])),
                "airport_origin_terminal": fb_sched_clean(fb_sched_get(fl, ["airport", "origin", "info", "terminal"])),
                "airport_origin_baggage": fb_sched_clean(fb_sched_get(fl, ["airport", "origin", "info", "baggage"])),
                "airport_destination_gate": fb_sched_clean(fb_sched_get(fl, ["airport", "destination", "info", "gate"])),
                "airport_destination_terminal": fb_sched_clean(fb_sched_get(fl, ["airport", "destination", "info", "terminal"])),
                "airport_destination_baggage": fb_sched_clean(fb_sched_get(fl, ["airport", "destination", "info", "baggage"])),
            }
            dep = fb_sched_get(fl, ["time", "scheduled", "departure"])
            if number not in items:
                items[number] = []
            items[number].append({"dep": dep, "fields": fields})
        except Exception as e:
            log.warning(f"{LOG_PREFIX}: skipped a malformed board row: {e}")
    cache[key] = {"at": now, "items": items}
    return items


def fb_sched_publish_gates():
    # Publish gate (departures) and belt (arrivals) for the whole airport board in
    # GATES_SENSOR as {flight number: [gate, terminal, belt]}. Never raises.
    if not PUBLISH_BOARD_GATES:
        return True
    try:
        home = None
        try:
            home = state.get(HOME_AIRPORT_ENTITY)
        except Exception:
            home = None
        home = fb_sched_norm(home)
        if not home or home in ("UNKNOWN", "UNAVAILABLE"):
            return True
        out = {"departures": {}, "arrivals": {}}
        for mode, side in [("departures", "origin"), ("arrivals", "destination")]:
            items = fb_sched_board(home, mode)
            for number in items:
                entries = items[number]
                if not entries:
                    continue
                fields = entries[0]["fields"]
                row = [
                    fields.get("airport_" + side + "_gate"),
                    fields.get("airport_" + side + "_terminal"),
                    fields.get("airport_" + side + "_baggage"),
                ]
                if row[0] or row[1] or row[2]:
                    out[mode][number] = row
        state.set(
            GATES_SENSOR,
            value=len(out["departures"]) + len(out["arrivals"]),
            new_attributes={
                "departures": out["departures"],
                "arrivals": out["arrivals"],
                "airport": home,
                "icon": GATES_ICON,
                "friendly_name": GATES_NAME,
                "source": "flightradar24 airport board",
            },
        )
        return True
    except Exception as e:
        log.warning(f"{LOG_PREFIX}: could not publish {GATES_SENSOR}: {e}")
        return False


def fb_sched_add_board_gates(leg):
    # Fill gate, terminal and belt that are still empty from the airport board of the
    # airport the card shows. A failure only logs a warning.
    try:
        home = None
        try:
            home = state.get(HOME_AIRPORT_ENTITY)
        except Exception:
            home = None
        home = fb_sched_norm(home)
        if not home or home in ("UNKNOWN", "UNAVAILABLE"):
            return
        number = fb_sched_norm(leg.get("flight_number"))
        if not number:
            return
        modes = []
        for side, mode in [("origin", "departures"), ("destination", "arrivals")]:
            codes = [
                fb_sched_norm(leg.get("airport_" + side + "_code_icao")),
                fb_sched_norm(leg.get("airport_" + side + "_code_iata")),
            ]
            if home in codes:
                modes.append(mode)
        dep = leg.get("time_scheduled_departure")
        for mode in modes:
            items = fb_sched_board(home, mode)
            best = None
            best_dist = 0
            for entry in items.get(number, []):
                if entry["dep"] is None or dep is None:
                    continue
                dist = abs(entry["dep"] - dep)
                if dist <= BOARD_MATCH_SECONDS and (best is None or dist < best_dist):
                    best = entry
                    best_dist = dist
            if best is None:
                continue
            for key in best["fields"]:
                if best["fields"][key] and not leg.get(key):
                    leg[key] = best["fields"][key]
    except Exception as e:
        log.warning(f"{LOG_PREFIX}: airport board gates failed for {leg.get('flight_number')}: {e}")


def fb_sched_add_aerodatabox(code, leg):
    # Second gate source. Fills gate, terminal and belt that are still empty.
    # A failure only logs a warning: the leg is published without those values.
    if not AERODATABOX_API_KEY or leg is None:
        return
    number = fb_sched_norm(leg.get("flight_number") or code)
    dep = leg.get("time_scheduled_departure")
    arr = leg.get("time_scheduled_arrival")
    if not number or not dep:
        return
    now = time.time()
    near = abs(dep - now) < ADB_WINDOW_HOURS * 3600
    if arr is not None and abs(arr - now) < ADB_WINDOW_HOURS * 3600:
        near = True
    if not near:
        return
    cache = SCHEDULE_STATE["adb_cache"]
    entry = cache.get(code)
    fields = None
    if entry is not None and now - entry["at"] < ADB_CACHE_SECONDS:
        fields = entry["fields"]
    else:
        fields = {}
        try:
            day = time.strftime("%Y-%m-%d", time.gmtime(dep))
            url = AERODATABOX_URL.replace("{number}", number).replace("{date}", day)
            payload = fb_sched_http_json(
                url,
                headers={"X-RapidAPI-Key": AERODATABOX_API_KEY, "X-RapidAPI-Host": AERODATABOX_HOST},
            )
            items = payload if isinstance(payload, list) else []
            want_o = leg.get("airport_origin_code_iata")
            want_d = leg.get("airport_destination_code_iata")
            hit = None
            for item in items:
                o = fb_sched_get(item, ["departure", "airport", "iata"])
                d = fb_sched_get(item, ["arrival", "airport", "iata"])
                if o == want_o and d == want_d:
                    hit = item
                    break
            if hit is None and len(items) == 1:
                hit = items[0]
            if hit is not None:
                fields = {
                    "airport_origin_gate": fb_sched_clean(fb_sched_get(hit, ["departure", "gate"])),
                    "airport_origin_terminal": fb_sched_clean(fb_sched_get(hit, ["departure", "terminal"])),
                    "airport_destination_gate": fb_sched_clean(fb_sched_get(hit, ["arrival", "gate"])),
                    "airport_destination_terminal": fb_sched_clean(fb_sched_get(hit, ["arrival", "terminal"])),
                    "airport_destination_baggage": fb_sched_clean(fb_sched_get(hit, ["arrival", "baggageBelt"])),
                }
        except Exception as e:
            log.warning(f"{LOG_PREFIX}: AeroDataBox lookup for {code} failed: {e}")
        cache[code] = {"at": now, "fields": fields}
    for key in fields:
        if fields[key] and not leg.get(key):
            leg[key] = fields[key]


def fb_sched_avs_merge(code, leg):
    # Fills empty gate, terminal and belt from the Aviationstack cache. This never
    # makes a request, so the periodic rebuild cannot use up the free quota.
    if leg is None:
        return
    entry = SCHEDULE_STATE["avs_cache"].get(code)
    if entry is None:
        return
    fields = entry["fields"]
    for key in fields:
        if key != "_live" and fields[key] and not leg.get(key):
            leg[key] = fields[key]


def fb_sched_avs_lookup(code):
    # ONE Aviationstack request for a flight the user clicked. Returns True when
    # new data was stored. Any failure only logs a warning (the board keeps working).
    if not AVIATIONSTACK_API_KEY:
        return False
    now = time.time()
    entry = SCHEDULE_STATE["avs_cache"].get(code)
    if entry is not None and now - entry["at"] < AVS_CACHE_SECONDS:
        return False
    usage = SCHEDULE_STATE["avs_usage"]
    month = time.strftime("%Y-%m", time.gmtime(now))
    if usage["month"] != month:
        usage["month"] = month
        usage["count"] = 0
    if usage["count"] >= AVS_MONTHLY_LIMIT:
        log.warning(f"{LOG_PREFIX}: Aviationstack monthly safety limit ({AVS_MONTHLY_LIMIT}) reached, not asking for {code}")
        return False
    fields = {}
    try:
        usage["count"] = usage["count"] + 1
        query = urllib.parse.urlencode({"access_key": AVIATIONSTACK_API_KEY, "flight_iata": code, "limit": 10})
        payload = fb_sched_http_json(AVIATIONSTACK_URL + "?" + query)
        err = fb_sched_get(payload, ["error"])
        if err:
            # e.g. usage_limit_reached, invalid_access_key: never include the key in a message
            log.warning(f"{LOG_PREFIX}: Aviationstack refused {code}: {fb_sched_get(err, ['code'])} {fb_sched_get(err, ['message'])}")
            fb_sched_notify_error(f"Aviationstack: {fb_sched_get(err, ['code'])}")
            SCHEDULE_STATE["avs_cache"][code] = {"at": now, "fields": {}}
            return False
        items = fb_sched_get(payload, ["data"]) or []
        if not isinstance(items, list):
            items = []
        # Prefer the flight whose departure is closest to now
        best = None
        best_gap = None
        for item in items:
            sched = fb_sched_get(item, ["departure", "scheduled"])
            gap = 10 ** 9
            try:
                if sched:
                    gap = abs(time.mktime(time.strptime(str(sched)[:19], "%Y-%m-%dT%H:%M:%S")) - now)
            except Exception:
                gap = 10 ** 9
            if best is None or gap < best_gap:
                best = item
                best_gap = gap
        if best is not None:
            fields = {
                "airport_origin_gate": fb_sched_clean(fb_sched_get(best, ["departure", "gate"])),
                "airport_origin_terminal": fb_sched_clean(fb_sched_get(best, ["departure", "terminal"])),
                "airport_destination_gate": fb_sched_clean(fb_sched_get(best, ["arrival", "gate"])),
                "airport_destination_terminal": fb_sched_clean(fb_sched_get(best, ["arrival", "terminal"])),
                "airport_destination_baggage": fb_sched_clean(fb_sched_get(best, ["arrival", "baggage"])),
            }
            # Live position, when the plan returns it (kept apart from the gate fields)
            live = fb_sched_get(best, ["live"])
            if isinstance(live, dict) and live.get("latitude") is not None and live.get("longitude") is not None:
                try:
                    fields["_live"] = {
                        "os_latitude": float(live.get("latitude")),
                        "os_longitude": float(live.get("longitude")),
                        "os_heading": live.get("direction"),
                        "os_on_ground": bool(live.get("is_ground")),
                        "os_time": now,
                        "os_source": "Aviationstack",
                    }
                except Exception:
                    pass
        SCHEDULE_STATE["avs_cache"][code] = {"at": now, "fields": fields}
        log.info(f"{LOG_PREFIX}: Aviationstack {code}: {len(items)} result(s), request {usage['count']} this month, fields {fields}")
        return True
    except Exception as e:
        log.warning(f"{LOG_PREFIX}: Aviationstack lookup for {code} failed: {e}")
        return False


def fb_sched_fetch(code):
    # Download the flight list for one flight number and return the best leg (dict) or None.
    # Raises on network or parse errors so the caller can log and keep the old data.
    url = FR24_URL.replace("{query}", code.lower())
    payload = fb_sched_http_json(url)
    items = fb_sched_get(payload, ["result", "response", "data"])
    if not items:
        return None
    legs = []
    for item in items:
        try:
            legs.append(fb_sched_leg(item))
        except Exception as e:
            log.warning(f"{LOG_PREFIX}: skipped a malformed leg for {code}: {e}")
    best = fb_sched_pick(legs, time.time())
    if best is not None:
        fb_sched_add_details(best)
        fb_sched_add_board_gates(best)
        fb_sched_add_aerodatabox(code, best)
        fb_sched_avs_merge(code, best)
    return best


# ---------------------------- OpenSky ---------------------------------------

def fb_sched_os_headers():
    # Authorization header for OpenSky, or {} for anonymous use. Never raises:
    # when the login fails the request simply goes out anonymously.
    if not OPENSKY_CLIENT_ID or not OPENSKY_CLIENT_SECRET:
        return {}
    try:
        now = time.time()
        tok = SCHEDULE_STATE["token"]
        if tok["value"] and tok["expires"] - 60 > now:
            return {"Authorization": "Bearer " + tok["value"]}
        body = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": OPENSKY_CLIENT_ID,
            "client_secret": OPENSKY_CLIENT_SECRET,
        }).encode("utf-8")
        payload = fb_sched_http_json(
            OPENSKY_TOKEN_URL,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=body,
        )
        value = payload.get("access_token")
        if not value:
            return {}
        tok["value"] = value
        tok["expires"] = now + float(payload.get("expires_in") or 300)
        return {"Authorization": "Bearer " + value}
    except Exception as e:
        log.warning(f"{LOG_PREFIX}: OpenSky login failed, using anonymous access: {e}")
        return {}


def fb_sched_os_state(row):
    # Turn one OpenSky state vector (a list) into the fields the card uses.
    def at(i):
        if len(row) > i:
            return row[i]
        return None
    return {
        "os_icao24": at(0),
        "os_callsign": fb_sched_clean(at(1)),
        "os_time": at(3) or at(4),
        "os_longitude": at(5),
        "os_latitude": at(6),
        "os_altitude_m": at(7) if at(7) is not None else at(13),
        "os_on_ground": bool(at(8)),
        "os_speed_ms": at(9),
        "os_heading": at(10),
        "os_vertical_rate_ms": at(11),
    }


def fb_sched_os_fetch(code, icao24, lat, lon, callsigns):
    # Ask OpenSky for one aircraft. Returns a dict of os_* fields, or None when it is
    # not heard right now. Raises on network errors.
    if icao24:
        url = OPENSKY_STATES_URL + "?" + urllib.parse.urlencode({"icao24": str(icao24).lower()})
    elif lat is not None and lon is not None:
        d = OPENSKY_BOX_DEGREES
        url = OPENSKY_STATES_URL + "?" + urllib.parse.urlencode({
            "lamin": round(float(lat) - d, 4), "lamax": round(float(lat) + d, 4),
            "lomin": round(float(lon) - d, 4), "lomax": round(float(lon) + d, 4),
        })
    else:
        return None
    payload = fb_sched_http_json(url, headers=fb_sched_os_headers())
    states = payload.get("states") if isinstance(payload, dict) else None
    if not states:
        return None
    if icao24:
        return fb_sched_os_state(states[0])
    # Box search: keep the aircraft whose callsign matches this flight
    for row in states:
        try:
            cs = fb_sched_norm(row[1] if len(row) > 1 else "")
            if cs and cs in callsigns:
                return fb_sched_os_state(row)
        except Exception:
            continue
    return None


def fb_sched_os_batch(icaos):
    # One request for many aircraft: returns {icao24: os_* fields}. Raises on errors.
    out = {}
    if not icaos:
        return out
    query = urllib.parse.urlencode([("icao24", str(i).lower()) for i in icaos])
    payload = fb_sched_http_json(OPENSKY_STATES_URL + "?" + query, headers=fb_sched_os_headers())
    states = payload.get("states") if isinstance(payload, dict) else None
    for row in states or []:
        try:
            out[str(row[0]).lower()] = fb_sched_os_state(row)
        except Exception:
            continue
    return out


def fb_sched_os_wait(err):
    # Seconds to wait when OpenSky answered "too many requests" (HTTP 429), else 0
    try:
        if isinstance(err, urllib.error.HTTPError) and err.code == 429:
            wait = 0
            try:
                wait = int(float(err.headers.get("X-Rate-Limit-Retry-After-Seconds") or 0))
            except Exception:
                wait = 0
            return max(wait, 60) if wait else OPENSKY_BACKOFF_SECONDS
    except Exception:
        pass
    return 0


def fb_sched_airborne(leg, hint):
    # True when the flight is in the air (OpenSky is only asked for those)
    if hint and hint.get("lat") is not None:
        return True
    if leg is None:
        return False
    if leg.get("is_live"):
        return True
    return bool(leg.get("time_real_departure")) and not leg.get("time_real_arrival")


# ---------------------------- flights to look up -----------------------------

def fb_sched_codes():
    # Returns (codes, hints). hints[code] = {"icao24", "lat", "lon"} taken from the
    # integration's live data, used to find the aircraft in OpenSky.
    codes = []
    hints = {}
    try:
        attrs = state.getattr(TRACKED_SENSOR)
        flights = []
        if attrs:
            flights = attrs.get("flights") or []
        for flight in flights:
            code = fb_sched_norm(flight.get("flight_number") or flight.get("callsign"))
            if not code:
                continue
            if code not in codes:
                codes.append(code)
            if flight.get("tracked_type") == "live":
                hints[code] = {
                    "icao24": fb_sched_clean(flight.get("icao_24bit")),
                    "lat": flight.get("latitude"),
                    "lon": flight.get("longitude"),
                    "callsign": fb_sched_norm(flight.get("callsign")),
                }
    except Exception as e:
        log.warning(f"{LOG_PREFIX}: could not read {TRACKED_SENSOR}: {e}")
    for extra in EXTRA_FLIGHTS:
        code = fb_sched_norm(extra)
        if code and code not in codes:
            codes.append(code)
    # Flights the card asked about; expired requests are dropped
    now = time.time()
    watch = SCHEDULE_STATE["watch"]
    for code in list(watch.keys()):
        if watch[code] < now:
            watch.pop(code, None)
        elif code not in codes:
            codes.append(code)
    return codes, hints


# ---------------------------- position fallbacks ------------------------------

def fb_sched_pos_fresh(leg, now):
    # True when the leg has a position newer than POSITION_STALE_SECONDS
    if leg.get("os_latitude") is None or leg.get("os_longitude") is None:
        return False
    when = leg.get("os_time")
    try:
        return when is not None and now - float(when) < POSITION_STALE_SECONDS
    except Exception:
        return False


def fb_sched_trail_position(code, leg):
    # Latest point of the Flightradar24 flight track (detail view). Cached per flight.
    # Returns a dict of os_* fields or None. Never raises.
    now = time.time()
    entry = SCHEDULE_STATE["trail_cache"].get(code)
    if entry is not None and now - entry["at"] < TRAIL_CACHE_SECONDS:
        return entry["data"]
    data = None
    flight_id = leg.get("flight_id")
    if flight_id:
        try:
            payload = fb_sched_http_json(FR24_DETAIL_URL.replace("{flight_id}", str(flight_id)))
            trail = fb_sched_get(payload, ["trail"])
            if isinstance(trail, list) and len(trail) > 0:
                # Newest point first; take the one with the highest timestamp to be safe
                best = None
                for pt in trail:
                    if isinstance(pt, dict) and pt.get("lat") is not None and pt.get("lng") is not None:
                        if best is None or (pt.get("ts") or 0) > (best.get("ts") or 0):
                            best = pt
                if best is not None:
                    alt = best.get("alt")
                    spd = best.get("spd")
                    data = {
                        "os_latitude": float(best.get("lat")),
                        "os_longitude": float(best.get("lng")),
                        "os_altitude_m": float(alt) * 0.3048 if alt is not None else None,
                        "os_speed_ms": float(spd) * 0.514444 if spd is not None else None,
                        "os_heading": best.get("hd"),
                        "os_on_ground": bool(alt is not None and float(alt) <= 0),
                        "os_time": best.get("ts") or now,
                        "os_source": "Flightradar24 track",
                    }
        except Exception as e:
            log.warning(f"{LOG_PREFIX}: Flightradar24 track for {code} failed: {e}")
    SCHEDULE_STATE["trail_cache"][code] = {"at": now, "data": data}
    return data


def fb_sched_estimate_position(leg, now):
    # Straight line between the airports, placed by elapsed time. Returns os_* fields or None.
    try:
        la1 = leg.get("airport_origin_latitude")
        lo1 = leg.get("airport_origin_longitude")
        la2 = leg.get("airport_destination_latitude")
        lo2 = leg.get("airport_destination_longitude")
        if la1 is None or lo1 is None or la2 is None or lo2 is None:
            return None
        t0 = leg.get("time_real_departure") or leg.get("time_estimated_departure") or leg.get("time_scheduled_departure")
        t1 = leg.get("time_estimated_arrival") or leg.get("time_scheduled_arrival")
        if not t0 or not t1 or t1 <= t0:
            return None
        frac = (now - t0) / float(t1 - t0)
        if frac < 0:
            frac = 0.0
        if frac > 1:
            frac = 1.0
        p1 = math.radians(float(la1))
        l1 = math.radians(float(lo1))
        p2 = math.radians(float(la2))
        l2 = math.radians(float(lo2))
        d = 2 * math.asin(math.sqrt(math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2))
        if d < 1e-9:
            lat = float(la1)
            lon = float(lo1)
        else:
            a = math.sin((1 - frac) * d) / math.sin(d)
            b = math.sin(frac * d) / math.sin(d)
            x = a * math.cos(p1) * math.cos(l1) + b * math.cos(p2) * math.cos(l2)
            y = a * math.cos(p1) * math.sin(l1) + b * math.cos(p2) * math.sin(l2)
            z = a * math.sin(p1) + b * math.sin(p2)
            lat = math.degrees(math.atan2(z, math.sqrt(x * x + y * y)))
            lon = math.degrees(math.atan2(y, x))
        # Heading: from the estimated point toward the destination
        pl = math.radians(lat)
        ll = math.radians(lon)
        hy = math.sin(l2 - ll) * math.cos(p2)
        hx = math.cos(pl) * math.sin(p2) - math.sin(pl) * math.cos(p2) * math.cos(l2 - ll)
        heading = (math.degrees(math.atan2(hy, hx)) + 360) % 360
        return {
            "os_latitude": round(lat, 4),
            "os_longitude": round(lon, 4),
            "os_heading": round(heading),
            "os_on_ground": False,
            "os_time": now,
            "os_source": "Estimated",
        }
    except Exception as e:
        log.warning(f"{LOG_PREFIX}: position estimate failed: {e}")
        return None


def fb_sched_fallback_position(code, leg, hint):
    # Fills the leg's position from the next source when OpenSky has none (or only an
    # old one). Only for flights in the air. Never raises; the leg stays usable.
    try:
        now = time.time()
        if fb_sched_pos_fresh(leg, now):
            return
        if not fb_sched_airborne(leg, hint):
            return
        stale = None
        if leg.get("os_latitude") is not None:
            stale = {}
            for key in leg:
                if key.startswith("os_"):
                    stale[key] = leg[key]
        # 1. Position the Flightradar24 integration already knows
        got = None
        if hint and hint.get("lat") is not None and hint.get("lon") is not None:
            try:
                got = {"os_latitude": float(hint["lat"]), "os_longitude": float(hint["lon"]), "os_on_ground": False,
                       "os_time": now, "os_source": "Flightradar24"}
            except Exception:
                got = None
        # 2. Flightradar24 flight track
        if got is None:
            got = fb_sched_trail_position(code, leg)
        # 3. Aviationstack (filled only by a click)
        if got is None:
            entry = SCHEDULE_STATE["avs_cache"].get(code)
            if entry is not None and entry["fields"].get("_live"):
                got = entry["fields"]["_live"]
        # 4. Old OpenSky position beats a guess
        if got is None and stale is not None:
            got = stale
            got["os_source"] = "OpenSky (last known)"
        # 5. Estimate along the route
        if got is None and POSITION_ESTIMATE:
            got = fb_sched_estimate_position(leg, now)
        if got:
            for key in got:
                leg[key] = got[key]
    except Exception as e:
        log.warning(f"{LOG_PREFIX}: position fallback for {code} failed: {e}")


# =============================================================================
# REBUILD
# =============================================================================

def fb_sched_rebuild():
    # Look up what is needed and publish OUT_SENSOR. Each flight is handled on its
    # own so one failure never blocks the others. Never raises.
    cache = SCHEDULE_STATE["cache"]
    os_cache = SCHEDULE_STATE["os_cache"]
    now = time.time()
    codes, hints = fb_sched_codes()
    failures = []
    os_failures = []

    for code in codes:
        # ---- Flightradar24: schedule, gate, terminal, belt ----
        entry = None
        try:
            entry = cache.get(code)
            if entry is None or now - entry["at"] >= CACHE_SECONDS:
                leg = fb_sched_fetch(code)
                cache[code] = {"at": now, "leg": leg}
                if leg is None:
                    log.info(f"{LOG_PREFIX}: Flightradar24 has no schedule for {code}")
        except Exception as e:
            # Keep the previous data (if any) and retry on the next refresh
            log.warning(f"{LOG_PREFIX}: lookup for {code} failed: {e}")
            failures.append(code)
            if entry is not None:
                cache[code] = {"at": now - CACHE_SECONDS + 60, "leg": entry["leg"]}

    # ---- OpenSky: live position (airborne flights only), one request for all ----
    if OPENSKY_ENABLED:
        try:
            blocked = SCHEDULE_STATE["os_block_until"] - now
            todo = []          # (code, icao24, lat, lon, callsigns)
            for code in codes:
                try:
                    leg_now = None
                    if cache.get(code) is not None:
                        leg_now = cache[code]["leg"]
                    hint = hints.get(code)
                    if not fb_sched_airborne(leg_now, hint):
                        os_cache.pop(code, None)
                        continue
                    oentry = os_cache.get(code)
                    if oentry is not None and now - oentry["at"] < OPENSKY_REFRESH_SECONDS:
                        continue
                    icao24 = None
                    lat = None
                    lon = None
                    callsigns = [code]
                    if hint:
                        icao24 = hint.get("icao24")
                        lat = hint.get("lat")
                        lon = hint.get("lon")
                        if hint.get("callsign"):
                            callsigns.append(hint["callsign"])
                    if leg_now:
                        if not icao24:
                            icao24 = leg_now.get("aircraft_hex")
                        if leg_now.get("callsign"):
                            callsigns.append(fb_sched_norm(leg_now["callsign"]))
                    todo.append((code, icao24, lat, lon, callsigns))
                except Exception as e:
                    log.warning(f"{LOG_PREFIX}: OpenSky preparation for {code} failed: {e}")
            if todo and blocked > 0:
                # OpenSky asked us to slow down: keep the last position we had
                pass
            elif todo:
                known = [t[1] for t in todo if t[1]]
                found = {}
                try:
                    found = fb_sched_os_batch(known)
                    for t in todo:
                        if t[1]:
                            data = found.get(str(t[1]).lower())
                            os_cache[t[0]] = {"at": now, "data": data}
                    # Aircraft without an id: search a box around the last known position
                    for t in todo:
                        if not t[1]:
                            try:
                                os_cache[t[0]] = {"at": now, "data": fb_sched_os_fetch(t[0], None, t[2], t[3], t[4])}
                            except Exception as e:
                                if fb_sched_os_wait(e):
                                    raise
                                log.warning(f"{LOG_PREFIX}: OpenSky lookup for {t[0]} failed: {e}")
                                os_failures.append(t[0])
                                old = os_cache.get(t[0])
                                if old is not None:
                                    os_cache[t[0]] = {"at": now - OPENSKY_REFRESH_SECONDS + 60, "data": old["data"]}
                except Exception as e:
                    wait = fb_sched_os_wait(e)
                    if wait:
                        SCHEDULE_STATE["os_block_until"] = now + wait
                        log.warning(
                            f"{LOG_PREFIX}: OpenSky says too many requests (HTTP 429). Pausing OpenSky for "
                            f"{int(wait / 60)} minutes and keeping the last known positions. "
                            "A free OpenSky account raises the daily limit a lot (see the top of this file)."
                        )
                    else:
                        log.warning(f"{LOG_PREFIX}: OpenSky request failed: {e}")
                    for t in todo:
                        os_failures.append(t[0])
                        old = os_cache.get(t[0])
                        if old is not None:
                            os_cache[t[0]] = {"at": now - OPENSKY_REFRESH_SECONDS + 60, "data": old["data"]}
        except Exception as e:
            log.warning(f"{LOG_PREFIX}: OpenSky step failed: {e}")

    try:
        # Only publish flights that are still wanted
        out = []
        for code in codes:
            entry = cache.get(code)
            if entry is None or entry["leg"] is None:
                continue
            leg = dict(entry["leg"])
            leg["query"] = code
            leg["schedule_fetched_at"] = entry["at"]
            oentry = os_cache.get(code)
            if oentry is not None and oentry["data"]:
                for key in oentry["data"]:
                    leg[key] = oentry["data"][key]
                leg["os_fetched_at"] = oentry["at"]
                if not leg.get("os_source"):
                    leg["os_source"] = "OpenSky"
            fb_sched_fallback_position(code, leg, hints.get(code))
            out.append(leg)
        # Forget flights that are no longer wanted
        for key in list(cache.keys()):
            if key not in codes:
                cache.pop(key, None)
        for key in list(os_cache.keys()):
            if key not in codes:
                os_cache.pop(key, None)

        state.set(
            OUT_SENSOR,
            value=len(out),
            new_attributes={
                "state_class": "total",
                "flights": out,
                "icon": OUT_ICON,
                "friendly_name": OUT_NAME,
                "source": "flightradar24 flight list + opensky states + position fallbacks",
            },
        )
    except Exception as e:
        log.error(f"{LOG_PREFIX}: failed publishing {OUT_SENSOR}: {e}")
        fb_sched_notify_error(f"Failed publishing {OUT_SENSOR}: {e}")
        return

    gates_ok = fb_sched_publish_gates()

    if failures:
        fb_sched_notify_error(
            "Could not get the schedule from Flightradar24 for: " + ", ".join(failures)
            + ". Flightradar24 may be blocking or have changed the endpoint. Check the log."
        )
    elif not gates_ok:
        fb_sched_notify_error(
            "Could not read the Flightradar24 airport board for the gate sensor "
            + GATES_SENSOR + ". Flightradar24 may be blocking or have changed the endpoint. Check the log."
        )
    elif os_failures:
        fb_sched_notify_error(
            "Could not get the live position from OpenSky for: " + ", ".join(os_failures)
            + ". OpenSky may be rate limiting you (add an account in the script). Check the log."
        )


def fb_sched_run():
    # Run one rebuild unless another one is already running.
    if SCHEDULE_STATE["busy"]:
        return False
    SCHEDULE_STATE["busy"] = True
    try:
        fb_sched_rebuild()
    except Exception as e:
        log.error(f"{LOG_PREFIX}: rebuild failed: {e}")
    finally:
        SCHEDULE_STATE["busy"] = False
    return True


# =============================================================================
# TRIGGERS AND SERVICES
# =============================================================================

@state_trigger(TRACKED_SENSOR)
@time_trigger("startup", f"period(00:00:00, {REFRESH_PERIOD_SECONDS}sec)")
def flight_board_schedule_refresh():
    # This is a rebuild (not a one-shot action), so the idempotency guard is
    # intentionally not used; re-running is always safe.
    fb_sched_run()


@service
def flight_board_lookup(code=None):
    # Called by the card (pyscript.flight_board_lookup) when you open a flight pop-up
    # or track a flight. Adds the flight to the watch list and looks it up now.
    # Example: service: pyscript.flight_board_lookup  data: {code: "DL1505"}
    try:
        norm = fb_sched_norm(code)
        if not norm:
            return
        now = time.time()
        known = norm in SCHEDULE_STATE["watch"] and SCHEDULE_STATE["cache"].get(norm) is not None
        SCHEDULE_STATE["watch"][norm] = now + WATCH_MINUTES * 60
        # Aviationstack (free plan): only asked here, when a flight is clicked
        fresh = False
        try:
            fresh = fb_sched_avs_lookup(norm)
        except Exception as e:
            log.warning(f"{LOG_PREFIX}: Aviationstack step failed for {norm}: {e}")
        if fresh:
            # Drop the cached leg so the next rebuild merges the new gate data
            SCHEDULE_STATE["cache"].pop(norm, None)
        if known and not fresh:
            # Already looked up recently; the periodic rebuild keeps it fresh
            return
        waited = 0
        while SCHEDULE_STATE["busy"] and waited < LOOKUP_WAIT_SECONDS:
            task.sleep(1)
            waited = waited + 1
        fb_sched_run()
    except Exception as e:
        log.error(f"{LOG_PREFIX}: lookup service failed for {code}: {e}")
