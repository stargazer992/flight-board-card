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
#   - Schedule, gate, terminal and belt come from the same Flightradar24 data
#     that the flightradar24.com flight page uses.
#   - OpenSky is only asked for flights that are airborne, at most once per
#     OPENSKY_REFRESH_SECONDS per flight.
#   - Results are cached so Flightradar24 is asked at most once per CACHE_SECONDS.
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
#   - OpenSky only knows aircraft that its receivers hear, so coverage varies.
#   - PyScript sensors are not saved across a full HA restart; the startup trigger
#     rebuilds the sensor every time PyScript loads.
#   - Only the Python standard library is used (urllib, json), no extra install.

import json
import time
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

# A flight is looked up at most once per this many seconds
CACHE_SECONDS = 900

# OpenSky Network (live position, second source)
OPENSKY_ENABLED = True
OPENSKY_CLIENT_ID = ""
OPENSKY_CLIENT_SECRET = ""
OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"
OPENSKY_TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
# Seconds between OpenSky requests for the same flight. Anonymous use has about
# 400 requests a day, so keep this at 120 or more unless you added an account.
OPENSKY_REFRESH_SECONDS = 120
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
    "watch": {},       # code -> expiry timestamp (asked by the card)
    "token": {"value": "", "expires": 0},
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
    return fb_sched_pick(legs, time.time())


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

        # ---- OpenSky: live position (airborne flights only) ----
        if not OPENSKY_ENABLED:
            continue
        oentry = None
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
            data = fb_sched_os_fetch(code, icao24, lat, lon, callsigns)
            os_cache[code] = {"at": now, "data": data}
        except Exception as e:
            log.warning(f"{LOG_PREFIX}: OpenSky lookup for {code} failed: {e}")
            os_failures.append(code)
            if oentry is not None:
                os_cache[code] = {"at": now - OPENSKY_REFRESH_SECONDS + 60, "data": oentry["data"]}

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
                "source": "flightradar24 flight list + opensky states",
            },
        )
    except Exception as e:
        log.error(f"{LOG_PREFIX}: failed publishing {OUT_SENSOR}: {e}")
        fb_sched_notify_error(f"Failed publishing {OUT_SENSOR}: {e}")
        return

    if failures:
        fb_sched_notify_error(
            "Could not get the schedule from Flightradar24 for: " + ", ".join(failures)
            + ". Flightradar24 may be blocking or have changed the endpoint. Check the log."
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
        if known:
            # Already looked up recently; the periodic rebuild keeps it fresh
            return
        waited = 0
        while SCHEDULE_STATE["busy"] and waited < LOOKUP_WAIT_SECONDS:
            task.sleep(1)
            waited = waited + 1
        fb_sched_run()
    except Exception as e:
        log.error(f"{LOG_PREFIX}: lookup service failed for {code}: {e}")
