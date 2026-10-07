# Changelog

## 1.10.0 (fork)
- Time zones: the flight pop-up shows departure times in the origin airport's local time and arrival times in the destination's, with the zone name (CDT, PDT). A **Times** button in the pop-up switches to the board airport's time for everything; the choice is remembered per device. New option `time_zone_mode` (`airport` or `board`). The board lists stay in the board airport's time.
- Auto rows now go up to 250 (was 60) so a long time window shows every flight; the Rows dropdown also offers 100 and 200.
- Pop-up: the plane emoji between the airports is now a clean dashed arrow, and times show as tidy Scheduled / Actual (or Estimated) cells instead of one long line.
- Time windows and airline filters now show every flight in the window: the companion script publishes a longer board (`sensor.flight_board_full`) and the card merges it in, because the integration only lists the next 50 flights. New option `full_board_entity`.
- Removed the LED dot-matrix style (a saved `theme: led` now shows Digital flaps).
- Phones: the dropdown menus stay on screen, and the Classic, Digital, Amsterdam, London and LED boards get smaller text and rebalanced columns so flight numbers and status are no longer cut off.
- Phones: the airport search, selectors and clock wrap onto the screen width instead of running off the side.
- Split-flap on phones: each table shrinks its tiles until the flight number, gate and times fit (the tracking row with a gate column was cut off).
- Click a column title to sort the board on it, in every style (Time, Destination/From, Flight, Gate, Status; Raleigh also City and Airline); click again to reverse. Remembered per device. Option `sort` sets the starting order.
- Phones: column titles and the DEPARTURES / ARRIVALS / TRACKING banner shrink on narrow panels so they no longer overlap or wrap (all styles except Raleigh and London, which have their own sizing).
- Script: position fallbacks so a flying aircraft always has a position: OpenSky, then Flightradar24 (integration position, flight track), Aviationstack (on click), then an estimate along the route. The pop-up names the source ("Position - Estimated"). Fresh OpenSky data always wins.
- Script: optional Aviationstack source (free plan) for gate, terminal and baggage belt, asked only when a flight is clicked, cached for an hour and capped per month.
- Raleigh: pop-up text is now readable (it was white on white).
- Companion script: OpenSky is now asked for all airborne flights in one request every 5 minutes (was one request per flight every 2 minutes), and pauses when OpenSky answers HTTP 429 (too many requests) instead of retrying every minute.
- Raleigh style closer to the real boards: option `sort: city` lists flights A-Z by city (airport code when codes are shown), `header_image` puts your own picture behind the DEPARTURES and ARRIVALS banner, and times read `01:45PM` (`compact_time`).
- Raleigh style on small screens: when city names do not fit (a phone), the board shows airport codes (ATL, MCO) instead of truncated names. Option `city_codes`: `auto`, `always` or `never`.
- New Rows dropdown next to the time window. The two work together: choosing a window shows every flight in it (up to `max_rows`), and choosing more rows than the window holds widens the window to the next one that has enough. `Auto` fits the rows to the window. Options: `show_rows_selector`, `row_options`, `max_rows`.
- New Raleigh style after the boards at Raleigh-Durham: blue banner, white rows, City / Time, Airline / Flight, Gate and Status columns, "On Time", orange new time when late, green Departed / Arrived / In Air. Airline logos are your own images through the new `airline_logos` option (none are bundled); without one the airline name is shown. A logo is matched by IATA code, ICAO code or the letters at the start of the flight number (e.g. `MX` and `MXY`), not case-sensitive. Flight numbers show a space after the airline code ("F9 3330").
- London style redone after the Heathrow boards: yellow banner with a black plane disc, pale header strip, yellow destinations and gates, white times and flight numbers, green Boarding, red Cancelled, and wording like "On time" and "Delayed to 12:20". New Gate column (departures) and Belt column (arrivals) for every flight, from the new `sensor.flight_board_gates` published by the companion script (option `gates_entity`).
- Click any flight on the board to open a details pop-up: aircraft, scheduled, estimated and actual times, gate, terminal and baggage belt at both airports, live position, altitude, speed, heading, vertical rate, distance to the destination and a countdown to landing or departure. Gate and terminal sit at the top of the pop-up in a compact yellow airport-sign block with black letters: the arrival gate (with baggage belt) for an arrival, the departure gate for a departure. Options `flight_popup`, `lookup_service`.
- Gate column (gate, terminal, belt) in the tracking panels. Option `show_gate`.
- Companion script now also reads gate, terminal and belt from Flightradar24, adds live position from OpenSky Network (optional account, `OPENSKY_*` settings) and has a `pyscript.flight_board_lookup` service that the card calls when you open a pop-up. It now covers flights that are already airborne too. Gates come from the Flightradar24 airport board (flights that have not departed yet) and the per-flight detail view (flights in the air), with an optional AeroDataBox key as a further source.

## 1.9.0 (fork)
- Optional schedule sensor (`schedule_entity`): flights that are not airborne yet show their route and scheduled time, with the date when it is not today. New companion PyScript in `extras/automation_flight_board_schedule.py`.

## 1.8.0 (fork)
- Tracker follows flights that are not on the airport board through the Flightradar24 integration (additional tracked sensor): live ETA, altitude and speed once airborne, "Not airborne yet" before. Tail numbers work too. New option `track_via_integration`.
- Credits now list stargazer992.

## 1.7.0 (fork)
- Track flight dropdown in the header: pick any flight on the board (filterable by flight, city or airline) to pin it; tap again to untrack.

## 1.6.0 (fork)
- Flight tracker: enter a flight number to pin its status in a Tracking panel above the board, and highlight it in the lists. Works with flight numbers and callsigns, ignores the other filters, and is remembered per device.
- New options `show_flight_tracker` and `tracked_flights`.

## 1.5.0 (fork)
- Add airlines to the dropdown from the card: pick from the airlines currently on the board or type a 2-letter code. Saved per device, removable with the x.
- Time window dropdown (Any time, Next 1/2/4/8/12/24 hours), configurable with `time_windows` and `time_window`, remembered per device.
- New options `allow_add_airlines`, `show_window_selector`, `time_windows`, `time_window`.

## 1.4.0 (fork)
- Airline filter dropdown (default AA, DL, UA, configurable with `airlines`), remembered per device.
- `hide_private` hides flights without an airline IATA code (on by default).
- Split-flap style: tiles scroll through the character drum before settling on the right letter or number. Options `flip_cycle`, `flip_on_load`, `flip_step_ms`, `flip_max_steps`.
- Only tiles whose text changed animate on updates.

## 1.3.1
- More room for the Status column (taken from Time and Flight, Destination unchanged).
- Status words switch to short forms (EXP, DELAY, DEP, CANCEL) only when the full word does not fit.

## 1.3.0
- First public release.
- Six board styles, selectable on the card: Classic, Split-flap, Digital flaps, Amsterdam style, London style, LED dot-matrix.
- Airport search with about 8,000 airports, plus a favourites list.
- Visual editor for all settings.
- 24-hour or 12-hour time format.
- Show departures, arrivals or both; side by side or stacked.
- Expected, delayed and landed times aligned in their own column.
- Board scales to fit any screen width.
- Clear message when the Flightradar24 integration is missing.
- Full width in Sections dashboards.
