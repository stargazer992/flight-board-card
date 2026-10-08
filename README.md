# Flight Board Card

> **Fork notice.** This is a fork of the excellent [flight-board-card](https://github.com/pmnilsson/flight-board-card) by **P-M Nilsson**, who created the card, the board styles and the airport search. All credit for the original goes to him. This fork adds an airline filter, a time window, a flight tracker and a scrolling split-flap animation (see the options below and the [changelog](CHANGELOG.md)). Fork additions by **[@stargazer992](https://github.com/stargazer992)**.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![Validate](https://github.com/stargazer992/flight-board-card/actions/workflows/validate.yml/badge.svg)](https://github.com/stargazer992/flight-board-card/actions/workflows/validate.yml)

An airport **departures and arrivals board** for your Home Assistant dashboard. It is built for wall panels and tablets: large, readable text, live status and seven classic board styles, including a split-flap board with flipping letters.

It shows the flights from the [Flightradar24 integration](https://github.com/AlexandrErohin/home-assistant-flightradar24). No Flightradar24 subscription is needed.

![Split-flap style with flipping letters](https://raw.githubusercontent.com/stargazer992/flight-board-card/main/images/splitflap-demo.gif)

## Features

- Departures and arrivals side by side (or stacked, or only one of them)
- **Added in this fork:**
  - **Airline filter**: dropdown on the card (AA, DL, UA by default); add or remove airlines right on the card, and hide private and charter flights
  - **Time window**: dropdown to show only the next 1, 2, 4, 8, 12 or 24 hours
  - **Flight tracker**: pick a flight from the board, or type a flight number or tail number, to pin its status in a Tracking panel. Flights that are not on the board yet are followed through the Flightradar24 integration (live ETA, altitude and speed once airborne), with an optional schedule script for flights that have not departed
  - **Flight pop-up**: click any flight on the board for its details: aircraft, scheduled, estimated and actual times, gate, terminal and baggage belt, live position, altitude, speed, distance to the destination and a countdown to landing (gate and position need the companion script)
  - **Gate column** in the tracking panels
  - **Split-flap flipping**: letters and numbers scroll through the drum before settling on the right character, like a real board
- Seven board styles, selectable from a menu on the card itself:
  - **Classic**: black and yellow
  - **Split-flap**: every letter on its own flap, letters flip when something changes
  - **Digital flaps**: modern flap-look panels
  - **Amsterdam style**: dark blue and yellow, clean and very readable
  - **London style**: Heathrow-inspired black and yellow, with a Gate and Belt column
  - **Raleigh style**: blue banner and white rows with City / Time, Airline / Flight, Gate and Status, like the boards at Raleigh-Durham
- Airport search on the card: type a name, city, IATA or ICAO code and pick from about 8,000 airports worldwide, with no setup or API key needed
- A short list of favourite airports is shown when you tap the search field. Use the built-in list or set your own.
- Times and clock in the airport's own local time zone, 24-hour or 12-hour format
- Expected, delayed and landed times aligned in their own column
- Colour-coded status: on time, expected, delayed, boarding, landed / departed, cancelled, diverted
- Visual editor: all settings can be changed in the card editor, no YAML needed
- Scales to fit any screen width
- The selected style is remembered per device, so each screen can have its own look

| Classic | Digital flaps |
|---|---|
| ![Classic](https://raw.githubusercontent.com/stargazer992/flight-board-card/main/images/classic.png) | ![Digital flaps](https://raw.githubusercontent.com/stargazer992/flight-board-card/main/images/digital.png) |
| **Amsterdam style** | **London style** |
| ![Amsterdam style](https://raw.githubusercontent.com/stargazer992/flight-board-card/main/images/amsterdam.png) | ![London style](https://raw.githubusercontent.com/stargazer992/flight-board-card/main/images/london.png) |
| **Raleigh style** | |
| ![Raleigh style](https://raw.githubusercontent.com/stargazer992/flight-board-card/main/images/raleigh.png) | |

## Requirements

1. Home Assistant 2024.1 or newer.
2. The **Flightradar24** integration ([AlexandrErohin/home-assistant-flightradar24](https://github.com/AlexandrErohin/home-assistant-flightradar24)), installed via HACS and added under Settings > Devices & services.

The integration creates these entities, which the card uses by default:

| Entity | Used for |
|---|---|
| `sensor.flightradar24_airport_departures` | departures |
| `sensor.flightradar24_airport_arrivals` | arrivals |
| `text.flightradar24_airport_track` | which airport is shown (ICAO code, e.g. `ESSA`) |

If the integration is missing, the card shows a message telling you what to install.

## Installation

### HACS (recommended)

1. Open HACS, click the three dots in the top right and choose **Custom repositories**.
2. Add `https://github.com/stargazer992/flight-board-card` with type **Dashboard**.
3. Search for **Flight Board Card** and click **Download**.
4. Reload your browser.

### Manual

1. Download `flight-board-card.js` from the latest release.
2. Copy it to `/config/www/flight-board-card.js`.
3. Add it as a resource: Settings > Dashboards > three dots > Resources > Add, URL `/local/flight-board-card.js`, type **JavaScript module**.

## Usage

Add the card from the card picker (search for "Flight Board") and change the settings in the visual editor, or use YAML:

```yaml
type: custom:flight-board-card
```

Full example:

```yaml
type: custom:flight-board-card
theme: splitflap
time_format: 24h
rows: 12
font_size: 22
show: both
layout: auto
past_minutes: 15
show_airline: true
show_selector: true
show_airport_selector: true
```

The board looks best on its own dashboard view with the **Panel (single card)** layout. In a **Sections** view it automatically takes the full width.

### Options

| Option | Default | Description |
|---|---|---|
| `theme` | `classic` | Starting style: `classic`, `splitflap`, `digital`, `amsterdam`, `london`, `raleigh`. (The old `led` value still works and shows Digital flaps.) A style picked in the menu on the card overrides this on that device. |
| `time_format` | `24h` | `24h` (18:30) or `12h` (6:30 PM) |
| `rows` | `12` | Number of flights shown in each list. Picking a time window on the card shows every flight in it (see `max_rows`) |
| `font_size` | `22` | Base text size in pixels |
| `show` | `both` | `both`, `departures`, `arrivals`, or `tracked` (only your tracked flights, a compact card for the main dashboard) |
| `layout` | `auto` | `auto` (side by side on wide screens) or `stacked` |
| `past_minutes` | `15` | How long departed or landed flights stay on the board |
| `show_airline` | `true` | Show the airline and airport code under the flight number and city |
| `show_selector` | `true` | Show the style menu on the card |
| `show_airport_selector` | `true` | Show the airport search field on the card |
| `show_airline_selector` | `true` | Show the airline filter dropdown (All / AA / DL / UA ...) on the card |
| `airlines` | AA, DL, UA | Airlines in the dropdown. Plain codes (`- AA`) or `{iata: AA, name: American}` entries |
| `airline` | (all) | Airline pre-selected at start. A choice made in the dropdown overrides it on that device |
| `allow_add_airlines` | `true` | Lets you add airlines to the dropdown on the card: pick one from "On the board now" or type a 2-letter code. Added airlines are saved on that device and can be removed with the x |
| `show_window_selector` | `true` | Show the time window dropdown (Any time / Next 1h ... 24h) on the card |
| `time_windows` | 1, 2, 4, 8, 12, 24 | Hours offered in the time window dropdown |
| `city_codes` | `auto` | Raleigh style: `auto` shows the airport code (ATL, MCO) instead of the city name when the names do not fit, for example on a phone; `always` or `never` forces it |
| `sort` | `time` | Starting order: `time`, `city`, `airline`, `flight`, `gate` or `status`. In every style you can click a column title (Time, Destination/From, Flight, Gate, Status; in Raleigh also City and Airline) to sort on it; click it again to reverse. The choice is remembered on that device. The nearest flights (per the time window and rows) are picked first, then sorted |
| `header_image` | (none) | Raleigh style: your own picture behind the DEPARTURES and ARRIVALS banner, for example `/local/logos/flightboard/header.jpg` (a wide image, about 1200 x 250 px, with the right side clear for the title) |
| `compact_time` | `true` | Raleigh style: times as `01:45PM` like the airport boards (12-hour clock) |
| `show_rows_selector` | `true` | Show the Rows dropdown on the card. Picking a time window grows the rows to fit every flight in it; picking more rows than the window holds widens the window |
| `row_options` | 6, 8, 10, 12, 16, 20, 30, 50, 100, 200 | Row counts offered in the Rows dropdown |
| `max_rows` | 250 | Most rows shown when the rows follow the time window |
| `time_window` | `0` | Time window selected at start in hours (`0` = any time). A choice made in the dropdown overrides it on that device |
| `show_flight_tracker` | `true` | Show the Track flight dropdown and the "Track a flight" field on the card |
| `track_via_integration` | `true` | Follow flights that are not on the board through the Flightradar24 integration's "Add to track" feature (see Flight tracker) |
| `schedule_entity` | `sensor.flight_board_schedule` | Optional sensor with the schedule of flights that are not airborne yet (see below) |
| `show_gate` | `true` | Show a Gate column (gate, terminal, baggage belt) in the tracking panels. Needs the companion script |
| `flight_popup` | `true` | Click any flight on the board to open a details pop-up (times, gate, baggage belt, position, altitude, time to landing) |
| `gates_entity` | `sensor.flight_board_gates` | London style only: sensor with the gate (departures) and baggage belt (arrivals) of every flight on the board. Published by the companion script |
| `track_remove_after_hours` | `2` | Stop tracking a flight this many hours after it lands (removed from this device's tracked list; flights in `tracked_flights` are only hidden). `0` = never |
| `tracked_timezone` | `home` on the tracked-only card, `airport` on the full board | Time zone of the Time column in the tracking panel: `home` (Home Assistant's own zone, e.g. Eastern), `airport` (the destination's local time) or a zone name such as `America/New_York` |
| `tracked_controls` | `false` | With `show: tracked`: also show the title, clock, style menu and Track flight box. Off = only the column titles and flight rows |
| `time_zone_mode` | `airport` | Pop-up times: `airport` = departure in the origin's local time and arrival in the destination's (with CDT/PDT etc.); `board` = everything in the board airport's time. The **Times** button in the pop-up switches it and is remembered per device |
| `full_board_entity` | `sensor.flight_board_full` | Longer list of flights from the companion script, merged into the board so long time windows and airline filters show all flights. Empty = off |
| `airline_logos` | (none) | Raleigh style: your own logo images by airline code, for example `{AA: /local/logos/aa.png, DL: /local/logos/dl.png}`. Put the image files in `/config/www/logos/`. Without a logo the airline name is shown as text. No logos are bundled with the card |
| `lookup_service` | `pyscript.flight_board_lookup` | Service of the companion script that the card calls to look up a flight |
| `tracked_flights` | (none) | Flight numbers always tracked, for example `[AA1234, DL567]`. Flights added on the card are saved on that device and can be removed with the x |
| `hide_private` | `true` | Hide private, charter and general-aviation flights (flights without an airline IATA code) |
| `flip_cycle` | `true` | Split-flap style only: letters and numbers scroll through the drum before settling, like a real board |
| `flip_on_load` | `true` | Spin every tile in from blank on first load |
| `flip_step_ms` | `55` | Milliseconds per character step (higher = slower) |
| `flip_max_steps` | `24` | Most characters a tile scrolls through before settling (lower = faster) |
| `flip_sound` | `false` | Play a real split-flap clatter once per board refresh, as long as the flipping lasts. Browsers only allow sound after you tap or click the page once |
| `flip_sound_volume` | `0.8` | Volume of the clatter, 0 to 1 (a refresh that changes only a few tiles is played quieter automatically) |
| `airports` | built-in list | Favourite airports shown when the search field is empty (see below) |
| `title` | airport name | Your own title instead of the airport name |
| `departures_entity` | `sensor.flightradar24_airport_departures` | Departures sensor |
| `arrivals_entity` | `sensor.flightradar24_airport_arrivals` | Arrivals sensor |
| `airport_entity` | `text.flightradar24_airport_track` | Text entity that holds the tracked airport |

Tip: on a public or shared screen, set `show_airport_selector: false` so nobody changes the airport by mistake.

### Favourite airports

```yaml
type: custom:flight-board-card
airports:
  - icao: ESSA
    iata: ARN
    name: Stockholm Arlanda
    tz: Europe/Stockholm
  - icao: KLAX
    iata: LAX
    name: Los Angeles
    tz: America/Los_Angeles
```

Any airport can be found with the search. The favourites are just quick picks. Built-in favourites: Stockholm Arlanda, Stockholm Bromma, Göteborg Landvetter, Copenhagen, Oslo, Helsinki, London Heathrow, Amsterdam Schiphol, Frankfurt, Paris CDG, Milano Malpensa, Zurich, Singapore Changi, Dubai and New York JFK.

### Flight tracker (fork)

Tap **Track flight** in the header and pick a flight from the list of flights on the board (filter by flight, city or airline; tap again to stop tracking). Or type a flight number (`AA1234`, or the callsign form `AAL1234`) in the "Track a flight" field and press Enter. The flight is pinned in a **Tracking** panel above the board, with its time, city, flight and status. It is also highlighted in the departures and arrivals lists. The tracker ignores the airline, time window and private-flight filters, and the `rows` limit.

```yaml
type: custom:flight-board-card
tracked_flights:
  - AA1234
  - DL567
```

**Flights that are not on the board.** The airport lists only reach a few hours ahead, so a flight that is further out is not on the board yet. For those, the card asks the Flightradar24 integration to follow the flight (it writes the number to `text.flightradar24_add_to_track`) and shows it from `sensor.flightradar24_additional_tracked`. Until the aircraft is airborne the integration only knows the flight number, so the panel shows "Not airborne yet". Once it is in the air you see origin or destination, ETA, altitude and ground speed, and after landing "Landed". Tail numbers (`N123AB`) work too. Flights added on the card are removed from the integration again when you remove them (set `track_via_integration: false` to turn this off). The integration's tracked list is shared by the whole Home Assistant installation. Times are shown in the airport's local time zone.

**Gates and flight details.** Tracked flights get a Gate column, and clicking any flight opens a pop-up with the gate in an airport-sign block, times, live position and a countdown. (Screenshots use sample data.)

![Tracking panels with a Gate column](https://raw.githubusercontent.com/stargazer992/flight-board-card/main/images/tracker-gates.png)

<img src="https://raw.githubusercontent.com/stargazer992/flight-board-card/main/images/flight-popup.png" alt="Flight pop-up with arrival gate, times and live position" width="420">

**Schedule for flights that have not departed (optional).** Before takeoff the integration knows nothing but the flight number. The optional PyScript [`extras/automation_flight_board_schedule.py`](extras/automation_flight_board_schedule.py) looks up the schedule on Flightradar24 for the flights the card is tracking and publishes it as `sensor.flight_board_schedule`. The card then shows the destination or origin and the scheduled time (with the date, for example `SCHED OCT 9`, when the flight leaves on another day), and switches to live data once the plane is airborne. It needs [PyScript](https://github.com/custom-components/pyscript) and uses an unofficial Flightradar24 web endpoint that can be blocked or change at any time; the script then keeps the last good data and sends one notification. Copy the file to your `pyscript` folder. **More hours than the integration lists.** The Flightradar24 integration only lists the next 50 flights per direction (about 3 hours at a busy airport), so a long time window or an airline filter would show only those. The script reads more pages of the same airport board and publishes them as `sensor.flight_board_full`; the card merges them in automatically (option `full_board_entity`, set it to an empty value to switch this off; in the script `FULL_BOARD_PAGES` sets how many pages of 100 flights, default 2, roughly 10 to 12 hours). These sensors are large, so keep them out of the database by adding this to your `configuration.yaml` (merge it with an existing `recorder:` block):

```yaml
recorder:
  exclude:
    entities:
      - sensor.flight_board_full
      - sensor.flight_board_schedule
```


**Gate, baggage belt and live position (optional, same script).** The same script also reads the departure and arrival gate, terminal and baggage belt from Flightradar24, and the live position (latitude, longitude, altitude, speed, heading, vertical rate) from [OpenSky Network](https://opensky-network.org/) as a second source. Both are published in `sensor.flight_board_schedule`. The card shows them in a Gate column in the tracking panels and in the flight pop-up (click any flight on the board). When you open a pop-up the card asks the script to look that flight up (`pyscript.flight_board_lookup`), and the data appears within a few seconds.

- Gates are often empty until a few hours before departure, and some airports never publish them. Empty values are simply not shown.
- The script also publishes `sensor.flight_board_gates` (gate for every departure, belt for every arrival at your airport). The London style shows it as a Gate / Belt column.
- The Flightradar24 flight list has no gates, so the script reads them from two other Flightradar24 sources: the airport board of the airport the card shows (flights that have not departed yet, refreshed every 10 minutes) and the detail view of a single flight (flights in the air). If that is empty too, an optional second source is [AeroDataBox](https://rapidapi.com/aedbx-aedbx/api/aerodatabox) (free RapidAPI plan): paste your key into `AERODATABOX_API_KEY` at the top of the script. It is only asked for flights within 8 hours of departure or landing and at most every 30 minutes per flight. A third optional source is [Aviationstack](https://aviationstack.com) (free plan, 100 requests a month): paste your key into `AVIATIONSTACK_API_KEY`. To protect the quota it is asked only when you click a flight, at most once an hour per flight and at most 90 times a month, and only to fill a gate, terminal or baggage belt that is still empty.
- OpenSky works without an account (about 400 credits a day). The script asks for all airborne flights in one request every 5 minutes, and when OpenSky answers "too many requests" (HTTP 429) it pauses OpenSky for the wait OpenSky sends (30 minutes if none) and keeps the last known positions. For more, create a free API client on opensky-network.org and put the client id and secret at the top of the script. Set `OPENSKY_ENABLED = False` to switch it off.
- OpenSky only knows aircraft its receivers hear, and it is only asked about flights that are in the air.
- "Time to gate" is shown as the time to landing (or to departure), because no source publishes a true time at the gate.

The flight is found on the board when it is in the data for the airport the board is showing. The Flightradar24 integration lists a limited number of flights to and from that airport, a few hours either side of now. A flight that is not there shows "is not on the board right now". If a flight number is used for both an arrival and a departure at the airport, both are shown.

### Raleigh style and airline logos (fork)

![Raleigh style with sample data](https://raw.githubusercontent.com/stargazer992/flight-board-card/main/images/raleigh.png)

The Raleigh style follows the boards at Raleigh-Durham: a blue banner, white rows, and City / Time, Airline / Flight, Gate and Status columns. Without logos it shows the airline name, as above. To show logos, add your own images (airline logos are trademarks, so none are bundled): put them in `/config/www/logos/` (about 60 px tall, transparent PNG or SVG) and map them by airline code:

```yaml
type: custom:flight-board-card
theme: raleigh
airline_logos:
  AA: /local/logos/aa.png
  DL: /local/logos/dl.png
  MX: /local/logos/breeze.png
  MXY: /local/logos/breeze.png
```

A logo is matched by the airline's IATA code, ICAO code or the letters at the start of the flight number, in any letter case.

### Airline filter (fork)

```yaml
type: custom:flight-board-card
theme: splitflap
airlines:
  - AA
  - DL
  - UA
  - iata: WN
    name: Southwest
```

The time window hides flights scheduled later than the chosen number of hours from now. The rows grow to fit the window (up to `max_rows`), and the Rows dropdown lets you pick a fixed number instead; asking for more rows than the window holds widens the window.

American Eagle, Delta Connection and United Express report their mainline code, so they appear under AA, DL and UA. With a single airline selected you may see fewer rows than `rows`, because only that airline's flights are listed. The selection is stored per device (browser localStorage).

## Good to know

- **Fork notice.** This fork adds the airline dropdown, private-flight hiding and the scrolling split-flap animation. Install it in HACS as a custom repository (type Dashboard) in place of the original; the card type stays `custom:flight-board-card`.

- **One airport per Home Assistant installation.** The Flightradar24 integration follows one airport at a time. Changing the airport on the card changes it for every screen and every card using the integration.
- **Switching airport takes a moment.** The board shows *Loading* until Flightradar24 has fetched the new airport's flights, usually 20–60 seconds depending on the integration's scan interval.
- **About the data.** The Flightradar24 integration uses Flightradar24's public, unofficial data feed. If Flightradar24 changes something on their side, flight data can stop updating until the integration is updated. That is outside this card's control. Please report data problems to the [integration](https://github.com/AlexandrErohin/home-assistant-flightradar24/issues) and display problems [here](https://github.com/pmnilsson/flight-board-card/issues).
- **Upgrading from an early version.** The old style names `solari`, `frankfurt`, `schiphol` and `heathrow` still work and are mapped to `splitflap`, `digital`, `amsterdam` and `london`.

## Airport data

The airport search uses a compact copy of the [mwgg/Airports](https://github.com/mwgg/Airports) database (MIT License), limited to airports that have an IATA code. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Disclaimer

This project is not affiliated with or endorsed by Flightradar24, any airport or any airport operator. The styles are original designs inspired by well-known types of departure boards. Flight data comes from the Flightradar24 integration and may be delayed or incomplete, so don't use it for real travel decisions.

## Credits

- **Original card:** [pmnilsson/flight-board-card](https://github.com/pmnilsson/flight-board-card) by P-M Nilsson (MIT).
- **Fork additions** (airline dropdown, time window, flight tracker, split-flap cycling): [@stargazer992](https://github.com/stargazer992).
- **Flight data:** the [Flightradar24 integration](https://github.com/AlexandrErohin/home-assistant-flightradar24) by Alexandr Erohin.
- **Airport data:** [mwgg/Airports](https://github.com/mwgg/Airports) (MIT).

## License

[MIT](LICENSE) © 2026 P-M Nilsson (original card), © 2026 stargazer992 (fork additions)

## Credits (sound)

The split-flap sound clip and the idea of playing it once per refresh come from [FlipOff](https://github.com/magnum6actual/flipoff) by magnum6actual (MIT licence).
