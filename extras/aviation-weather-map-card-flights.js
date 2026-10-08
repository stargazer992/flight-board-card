/*
 * aviation-weather-map-card-flights.js  (add-on, loaded as a second dashboard resource)
 * Adds a "tracked flights" layer to aviation-weather-map-card: route line, plane and airport labels for the flights
 * tracked on the flight-board-card (same browser). Options (in the weather card YAML, all optional):
 *   show_tracked_flights: true | flight_color: "#ffd600" | flight_refresh_seconds: 20
 *   flight_live_max_age: 600 | flight_remove_after_hours: 2
 */
(function () {
  const wait = (n) => {
    const C = customElements.get("aviation-weather-map-card");
    if (!C) return n > 0 && setTimeout(() => wait(n - 1), 250);
    const P = C.prototype;
    if (P._drawFlights) return;
    const css = `.awm-plane { background: none; border: none; }
.awm-plane svg { display: block; filter: drop-shadow(0 0 3px rgba(0,0,0,.9)); }
.awm-fl-label { background: rgba(0,0,0,.78); border: none; box-shadow: none; color: #ffd600; font-size: 11px; font-weight: 800; padding: 0 4px; border-radius: 3px; }
.awm-fl-label::before { display: none; }`;
    const cls = class {
  _initFlights() {
    this._teardownFlights();
    if (!this._cfg || this._cfg.show_tracked_flights === false || !this._L || !this._map) return;
    this._flGroup = this._L.layerGroup().addTo(this._map);
    this._flHandler = () => this._drawFlights();
    // both the normal card and the "-test" copy of it
    for (const p of ["flight-board-card", "flight-board-card-test"]) {
      window.addEventListener(p + "-geo", this._flHandler);
      window.addEventListener(p + "-tracked", this._flHandler);
    }
    window.addEventListener("storage", this._flHandler);
    this._flTimer = setInterval(() => { if (!document.hidden) this._drawFlights(); }, Math.max(5, Number(this._cfg.flight_refresh_seconds) || 20) * 1000);
    this._drawFlights();
  }

  _teardownFlights() {
    if (this._flTimer) clearInterval(this._flTimer);
    this._flTimer = null;
    if (this._flHandler) {
      for (const p of ["flight-board-card", "flight-board-card-test"]) {
        window.removeEventListener(p + "-geo", this._flHandler);
        window.removeEventListener(p + "-tracked", this._flHandler);
      }
      window.removeEventListener("storage", this._flHandler);
      this._flHandler = null;
    }
    this._flGroup = null;
  }

  _drawFlights() {
    try {
      const L = this._L, map = this._map, grp = this._flGroup;
      if (!L || !map || !grp) return;
      grp.clearLayers();
      let geo = [], tracked = [];
      for (const p of ["flight-board-card", "flight-board-card-test"]) {
        try { geo = geo.concat((JSON.parse(localStorage.getItem(p + "-geo") || "{}") || {}).flights || []); } catch (e) { /* ignore */ }
        try { tracked = tracked.concat(JSON.parse(localStorage.getItem(p + "-tracked") || "[]") || []); } catch (e) { /* ignore */ }
      }
      const T = tracked.map((x) => String(x).toUpperCase().replace(/[^A-Z0-9]/g, ""));
      const cfg = this._cfg, now = Date.now() / 1000, color = cfg.flight_color || "#ffd600";
      const rad = Math.PI / 180;
      for (const f of Array.isArray(geo) ? geo : []) {
        try {
          const keys = (f.keys || []).map((x) => String(x).toUpperCase());
          if (!f.yaml && !keys.some((k) => T.indexOf(k) >= 0)) continue;            // no longer tracked
          if (!f.o || !f.d || !f.o.ll || !f.d.ll) continue;
          const hrs = Number(cfg.flight_remove_after_hours) || 2;
          if (f.landed && f.arr && now > f.arr + hrs * 3600) continue;               // landed a while ago
          if (!f.landed && f.arr && now > f.arr + 6 * 3600) continue;                // stale record
          const A = f.o.ll, B = f.d.ll;
          // great-circle points, longitudes unwrapped so the line never jumps across the map
          const p1 = A[0] * rad, l1 = A[1] * rad, p2 = B[0] * rad, l2 = B[1] * rad;
          const dd = 2 * Math.asin(Math.sqrt(Math.sin((p2 - p1) / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin((l2 - l1) / 2) ** 2));
          const gc = (fr) => {
            if (!(dd > 1e-6)) return [A[0], A[1]];
            const a = Math.sin((1 - fr) * dd) / Math.sin(dd), b = Math.sin(fr * dd) / Math.sin(dd);
            const x = a * Math.cos(p1) * Math.cos(l1) + b * Math.cos(p2) * Math.cos(l2);
            const y = a * Math.cos(p1) * Math.sin(l1) + b * Math.cos(p2) * Math.sin(l2);
            const z = a * Math.sin(p1) + b * Math.sin(p2);
            return [Math.atan2(z, Math.sqrt(x * x + y * y)) / rad, Math.atan2(y, x) / rad];
          };
          const pts = [];
          let prev = A[1];
          for (let i = 0; i <= 64; i++) {
            const q = gc(i / 64);
            while (q[1] - prev > 180) q[1] -= 360;
            while (q[1] - prev < -180) q[1] += 360;
            prev = q[1];
            pts.push(q);
          }
          // progress from the departure and arrival times
          let prog = 0;
          if (f.landed) prog = 1;
          else if (f.dep && f.arr && f.arr > f.dep) prog = Math.max(0, Math.min(1, (now - f.dep) / (f.arr - f.dep)));
          const liveOk = f.live && !f.landed && now - (f.t || 0) <= (Number(cfg.flight_live_max_age) || 600);
          let pos, hdg;
          if (liveOk) {
            pos = [f.live[0], f.live[1]];
            if (pts.length) { const ref = pts[Math.round(prog * 64)]; while (pos[1] - ref[1] > 180) pos[1] -= 360; while (pos[1] - ref[1] < -180) pos[1] += 360; }
            hdg = f.live[2];
          } else {
            pos = gc(prog);
            const ref = pts[Math.round(prog * 64)]; if (ref) pos = [ref[0], ref[1]];
          }
          if (hdg === null || hdg === undefined || !isFinite(hdg)) {
            const i = Math.min(63, Math.round(prog * 64)), a = pts[i], b = pts[i + 1] || pts[i];
            hdg = (Math.atan2((b[1] - a[1]) * Math.cos(a[0] * rad), b[0] - a[0]) / rad + 360) % 360;
          }
          // route: solid up to the plane, dashed for the rest
          let cut = 0;
          for (let i = 0; i < pts.length; i++) if (i / 64 <= prog) cut = i;
          const done = pts.slice(0, cut + 1).concat([pos]), rest = [pos].concat(pts.slice(cut + 1));
          L.polyline(done, { color: color, weight: 3, opacity: 0.95, interactive: false }).addTo(grp);
          L.polyline(rest, { color: color, weight: 2, opacity: 0.8, dashArray: "6 7", interactive: false }).addTo(grp);
          // airport labels
          for (const end of [[f.o, A], [f.d, B]]) {
            L.circleMarker([end[1][0], end[1][1]], { radius: 4, color: "#000", weight: 1, fillColor: color, fillOpacity: 1, interactive: false })
              .bindTooltip(String(end[0].k || ""), { permanent: true, direction: "top", offset: [0, -4], className: "awm-fl-label" })
              .addTo(grp);
          }
          // plane
          const svg = '<svg width="30" height="30" viewBox="0 0 24 24" style="transform:rotate(' + Math.round(hdg) + 'deg)"><path d="M12 1.5c.9 0 1.5 1 1.5 2.4v5.6l8 4.6v2.2l-8-2.3v4.4l2.2 1.7v1.9L12 20.6 8.3 22v-1.9l2.2-1.7v-4.4l-8 2.3v-2.2l8-4.6V3.9c0-1.4.6-2.4 1.5-2.4z" fill="' + color + '" stroke="#000" stroke-width="1"/></svg>';
          const mk = L.marker([pos[0], pos[1]], {
            icon: L.divIcon({ className: "awm-plane", html: svg, iconSize: [30, 30], iconAnchor: [15, 15] }),
            zIndexOffset: 2000,
            keyboard: false,
          });
          const what = f.landed ? "Landed" : liveOk ? "Live position" : prog <= 0 ? "Not departed yet" : "Approx. " + Math.round(prog * 100) + "% of the way";
          mk.bindTooltip("<b>" + String(f.fl || "").replace(/</g, "") + "</b> " + String(f.o.k || "") + " &rarr; " + String(f.d.k || "") + "<br>" + what, { direction: "top", offset: [0, -12] });
          mk.addTo(grp);
        } catch (err) {
          console.warn("aviation-weather-map-card: could not draw a tracked flight", err);
        }
      }
    } catch (err) {
      console.warn("aviation-weather-map-card: tracked flights failed", err);
    }
  }

    }.prototype;
    for (const k of ["_initFlights", "_teardownFlights", "_drawFlights"]) P[k] = cls[k];
    const origInit = P._initMap, origTear = P._teardown;
    P._initMap = function () {
      const r = origInit.apply(this, arguments);
      try {
        if (this.shadowRoot && !this.shadowRoot.querySelector("style.awm-fl-css")) {
          const st = document.createElement("style");
          st.className = "awm-fl-css";
          st.textContent = css;
          this.shadowRoot.appendChild(st);
        }
        this._cfgFl = this._cfg;
        if (this._cfg && this._cfg.show_tracked_flights === undefined) this._cfg.show_tracked_flights = true;
        this._initFlights();
      } catch (e) { console.warn("aviation-weather-map-card flights add-on:", e); }
      return r;
    };
    P._teardown = function () {
      try { this._teardownFlights(); } catch (e) { /* ignore */ }
      return origTear.apply(this, arguments);
    };
    console.info("aviation-weather-map-card flights add-on loaded");
  };
  wait(80);
})();
