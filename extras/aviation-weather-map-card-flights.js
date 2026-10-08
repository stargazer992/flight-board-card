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
    this._flSig = "";
    this._flFitted = false;
  }

  _drawFlights() {
    try {
      const L = this._L, map = this._map, grp = this._flGroup;
      if (!L || !map || !grp) return;
      grp.clearLayers();
      if (this._flOff) { this._flSig = ""; return; }
      const shown = [], sigs = [];
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
          // Simple straight line A > B (not the real route); the plane sits on it
          const A = f.o.ll, B = [f.d.ll[0], f.d.ll[1]];
          while (B[1] - A[1] > 180) B[1] -= 360;
          while (B[1] - A[1] < -180) B[1] += 360;
          const nm = (p, q) => {
            const a1 = p[0] * rad, a2 = q[0] * rad, d1 = (q[0] - p[0]) * rad, d2 = (q[1] - p[1]) * rad;
            const h = Math.sin(d1 / 2) ** 2 + Math.cos(a1) * Math.cos(a2) * Math.sin(d2 / 2) ** 2;
            return 2 * 3440.065 * Math.asin(Math.min(1, Math.sqrt(h)));
          };
          const liveOk = f.live && !f.landed && now - (f.t || 0) <= (Number(cfg.flight_live_max_age) || 600);
          let prog = 0, how = "";
          if (f.landed) { prog = 1; how = "Landed"; }
          else if (liveOk) {
            // by distance: miles flown / (miles flown + miles to go), from the live position
            const lp = [f.live[0], f.live[1]];
            const d1 = nm(A, lp), d2 = nm(lp, f.d.ll);
            prog = d1 + d2 > 0 ? Math.max(0, Math.min(1, d1 / (d1 + d2))) : 0;
            how = "Live: " + Math.round(d2).toLocaleString("en-US") + " nm to go";
          } else if (f.dep && f.arr && f.arr > f.dep) {
            // by time: share of the scheduled / estimated flight time that has passed
            prog = Math.max(0, Math.min(1, (now - f.dep) / (f.arr - f.dep)));
            how = prog <= 0 ? "Not departed yet" : "Approx. " + Math.round(prog * 100) + "% of the way (by time)";
          }
          const pos = [A[0] + (B[0] - A[0]) * prog, A[1] + (B[1] - A[1]) * prog];
          // heading along the line as drawn on the map
          const pa = map.latLngToLayerPoint(L.latLng(A[0], A[1])), pb = map.latLngToLayerPoint(L.latLng(B[0], B[1]));
          const lineHdg = (Math.atan2(pb.x - pa.x, -(pb.y - pa.y)) * 180 / Math.PI + 360) % 360;
          // the flight's own heading (degrees, 0 = north, clockwise) when it is live and fresh; otherwise along the line
          const fh = f.live && f.live[2] !== null && f.live[2] !== undefined && f.live[2] !== "" ? Number(f.live[2]) : NaN;
          const hdg = liveOk && isFinite(fh) && fh >= 0 && fh <= 360 ? fh : lineHdg;
          shown.push(A, B);
          sigs.push((f.keys || [])[0] || f.fl);
          L.polyline([A, pos], { color: color, weight: 3, opacity: 0.95, interactive: false }).addTo(grp);
          L.polyline([pos, B], { color: color, weight: 2, opacity: 0.8, dashArray: "6 7", interactive: false }).addTo(grp);
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
          const what = how;
          mk.bindTooltip("<b>" + String(f.fl || "").replace(/</g, "") + "</b> " + String(f.o.k || "") + " &rarr; " + String(f.d.k || "") + "<br>" + what, { direction: "top", offset: [0, -12] });
          mk.addTo(grp);
        } catch (err) {
          console.warn("aviation-weather-map-card: could not draw a tracked flight", err);
        }
      }
      // Zoom out so the whole route(s) show, until you zoom / move the map yourself (a newly tracked flight zooms out again)
      const sig = sigs.sort().join("|");
      if (!shown.length) { this._flSig = ""; return; }
      if (sig !== this._flSig) {
        if (!this._viewReady || !map.getSize().x) { setTimeout(() => { try { this._drawFlights(); } catch (e) { /* ignore */ } }, 600); return; }
        this._flSig = sig;
        this._flManual = false;
        this._flFitted = true;
        map.fitBounds(L.latLngBounds(shown), { padding: [50, 50], maxZoom: 7, animate: false });
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
    // Menu: a Flights button in the bottom bar and a row in the legend switch the layer on / off (remembered in this browser)
    const KEY = "awm-flights-off";
    const count = (self) => { try { return self._flGroup ? self._flGroup.getLayers().filter((l) => l.options && l.options.zIndexOffset === 2000).length : 0; } catch (e) { return 0; } };
    const setOff = (self, off) => {
      self._flOff = off;
      try { localStorage.setItem(KEY, off ? "1" : "0"); } catch (e) { /* ignore */ }
      self._drawFlights();
      const b = self.shadowRoot && self.shadowRoot.querySelector(".bar [data-bar=flights]");
      if (b) b.classList.toggle("on", !off);
      const r = self.shadowRoot && self.shadowRoot.querySelector(".legend .row[data-flights]");
      if (r) r.classList.toggle("off", off);
    };
    const origLegend = P._renderLegend;
    P._renderLegend = function () {
      const r = origLegend.apply(this, arguments);
      try {
        const legend = this.shadowRoot && this.shadowRoot.querySelector(".legend");
        if (legend && this._cfg && this._cfg.show_tracked_flights !== false) {
          const row = document.createElement("div");
          row.className = "row" + (this._flOff ? " off" : "");
          row.setAttribute("data-flights", "1");
          row.innerHTML = '<span class="dot star">\u2708</span><span>Tracked flights</span><span class="count">' + count(this) + "</span>";
          row.addEventListener("click", () => setOff(this, !this._flOff));
          const h = document.createElement("div");
          h.className = "subhead";
          h.textContent = "Flights";
          legend.appendChild(h);
          legend.appendChild(row);
        }
      } catch (e) { /* ignore */ }
      return r;
    };
    const origFlInit = P._initFlights;
    P._initFlights = function () {
      try { if (this._flOff === undefined) this._flOff = localStorage.getItem(KEY) === "1"; } catch (e) { this._flOff = false; }
      const r = origFlInit.apply(this, arguments);
      try {
        const mapEl = this.shadowRoot && this.shadowRoot.querySelector(".map");
        if (mapEl) ["pointerdown", "wheel", "touchstart", "keydown"].forEach((evt) => mapEl.addEventListener(evt, () => { this._flManual = true; }, { passive: true }));
      } catch (e) { /* ignore */ }
      try {
        const bar = this.shadowRoot && this.shadowRoot.querySelector(".bar");
        if (bar && this._cfg && this._cfg.show_tracked_flights !== false && !bar.querySelector("[data-flights-btn]")) {
          const btn = document.createElement("button");
          btn.setAttribute("data-bar", "flights");
          btn.setAttribute("data-flights-btn", "1");
          btn.title = "Show / hide the tracked flights";
          btn.textContent = "\u2708 Flights";
          if (!this._flOff) btn.classList.add("on");
          btn.addEventListener("click", () => setOff(this, !this._flOff));
          bar.appendChild(btn);
        }
        this._renderLegend();
      } catch (e) { /* ignore */ }
      return r;
    };
    const origRefit = P._refit;
    P._refit = function () {
      if (this._flFitted && !this._flManual && this._flSig) return;   // keep the zoomed-out view of the tracked flight(s)
      return origRefit.apply(this, arguments);
    };
    P._teardown = function () {
      try { this._teardownFlights(); } catch (e) { /* ignore */ }
      return origTear.apply(this, arguments);
    };
    console.info("aviation-weather-map-card flights add-on loaded");
  };
  wait(80);
})();
