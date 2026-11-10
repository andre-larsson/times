// The front page's weather box, live from Open-Meteo (free for non-commercial sites, no key; data CC BY 4.0,
// credited in the box). It shows the paper's home town until the reader asks for their own position: the
// browser asks for permission, and the position is rounded to two decimals (about 1 km) before it leaves
// the page. The box then names the place the browser found (BigDataCloud's free reverse geocoding for
// browsers, no key) and shows its coordinates, accuracy and a map link, so a wrong fix (a VPN, an IP-based
// guess) is easy to spot. The choice, the last forecast (30 minutes) and the place names are kept in this
// browser.
(() => {
  "use strict";
  const box = document.querySelector("[data-weather]");
  if (!box) return;

  const API = "https://api.open-meteo.com/v1/forecast";
  const GEOCODE = "https://api.bigdatacloud.net/data/reverse-geocode-client";
  const FRESH_MS = 30 * 60 * 1000;
  const WHERE = "times:weather:where", CACHE = "times:weather:forecast", NAMES = "times:weather:names";
  const DAILY = ["weather_code", "temperature_2m_max", "temperature_2m_min", "precipitation_sum",
    "precipitation_probability_max", "wind_speed_10m_max", "sunrise", "sunset"];
  const HOURLY = ["temperature_2m", "weather_code"];
  // WMO weather interpretation codes, as Open-Meteo documents them
  const CONDITIONS = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy", 45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers", 85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorms", 96: "Thunder and hail", 99: "Thunder and hail",
  };

  const home = {
    place: box.dataset.place, lat: Number(box.dataset.lat), lon: Number(box.dataset.lon), here: false,
  };
  const hours = (box.dataset.hours || "").split(",").filter(Boolean).map(Number);
  const days = Number(box.dataset.days) || 2;
  const $ = (sel) => box.querySelector(sel);
  const field = (name) => box.querySelector(`[data-w="${name}"]`);
  const status = $("[data-weather-status]"), body = $("[data-weather-body]"), toggle = $("button[data-weather-where]");
  const canLocate = "geolocation" in navigator;

  const read = (key) => { try { return JSON.parse(localStorage.getItem(key)); } catch { return null; } };
  const write = (key, value) => {
    try { value == null ? localStorage.removeItem(key) : localStorage.setItem(key, JSON.stringify(value)); } catch { /* private mode */ }
  };
  const round = (x) => Math.round(x * 100) / 100;

  const deg = (t) => { const r = Math.round(t); return `${r < 0 ? "−" : ""}${Math.abs(r)}°`; };
  const condition = (code) => CONDITIONS[code] || "";
  const weekday = (date) => new Date(`${date}T12:00:00Z`).toLocaleDateString("en-GB", { weekday: "short", timeZone: "UTC" });
  function el(tag, cls, text) {
    const node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }
  function sep() {
    const node = el("span", "meta-sep", "·");
    node.setAttribute("aria-hidden", "true");
    return node;
  }

  function say(text) {
    status.textContent = text;
    status.hidden = !text;
  }

  // "±300 m", "±2 km": how sure the browser is (a fix from Wi-Fi is tight; one from the IP address is not)
  const accuracy = (m) => (m < 1000 ? `±${Math.max(100, Math.round(m / 100) * 100)} m` : `±${Math.round(m / 1000)} km`);

  function label(where) {
    const name = where.here ? (where.name || "Your location") : where.place;
    $(".block-sub").textContent = name;
    box.setAttribute("aria-label", where.here ? `Weather at your location${where.name ? `, ${where.name}` : ""}`
      : `Weather in ${where.place}`);
    toggle.textContent = where.here ? `Show ${home.place}` : "Use my location";
    box.querySelectorAll("[data-weather-where]").forEach((node) => { node.hidden = !canLocate; });

    // Where the browser placed the reader: the full place name, the rounded coordinates and a map
    const found = field("found");
    found.replaceChildren();
    if (where.here) {
      const lat = round(where.lat), lon = round(where.lon);
      const coords = `${Math.abs(lat).toFixed(2)}° ${lat < 0 ? "S" : "N"}, ${Math.abs(lon).toFixed(2)}° ${lon < 0 ? "W" : "E"}`;
      const map = el("a", "meta-link", "Map");
      map.href = `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lon}#map=11/${lat}/${lon}`;
      found.append(el("span", "", `Found: ${where.full || where.name || "a place without a name"}`), sep(),
        el("span", "", where.accuracy ? `${coords} (${accuracy(where.accuracy)})` : coords), sep(), map);
    }
    found.hidden = !where.here;
  }

  // The browser gives coordinates only; BigDataCloud turns them into a town and a country
  async function placeName(where) {
    const lat = round(where.lat), lon = round(where.lon), key = `${lat},${lon}`;
    const names = read(NAMES) || {};
    if (names[key]) return names[key];
    const params = new URLSearchParams({ latitude: String(lat), longitude: String(lon), localityLanguage: "en" });
    const res = await fetch(`${GEOCODE}?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const town = data.city || data.locality || "";
    if (!town && !data.countryName) throw new Error("no name");
    let country = data.countryName || "";
    try { country = new Intl.DisplayNames(["en"], { type: "region" }).of(data.countryCode) || country; } catch { /* keep */ }
    const region = (data.principalSubdivision || "").replace(/\s*\[[^\]]*\]$/, "");   // "Stockholms lan [SE-01]"
    const full = [town, region, country].filter((x, i, all) => x && all.indexOf(x) === i).join(", ");
    const named = { name: town || country, full };
    const keep = Object.fromEntries(Object.entries(names).slice(-9));   // the last few places are plenty
    keep[key] = named;
    write(NAMES, keep);
    return named;
  }

  // Open-Meteo's columns → today, the hours still ahead today, and the next days
  function render(data) {
    const d = data.daily;
    const now = data.current?.time
      || new Date(Date.now() + (data.utc_offset_seconds || 0) * 1000).toISOString().slice(0, 16);
    const today = now.slice(0, 10), hour = Number(now.slice(11, 13));
    const i = d.time.indexOf(today);
    if (i < 0 || d.temperature_2m_max[i] == null) throw new Error(`no forecast for ${today}`);

    field("high").textContent = deg(d.temperature_2m_max[i]);
    field("low").textContent = deg(d.temperature_2m_min[i]);
    field("condition").textContent = condition(d.weather_code[i]);
    const nowTemp = data.current?.temperature_2m;
    field("now").textContent = nowTemp == null ? "" : `Now ${deg(nowTemp)}`;
    field("now").hidden = nowTemp == null;
    const chance = d.precipitation_probability_max[i], mm = Math.round((d.precipitation_sum[i] || 0) * 10) / 10;
    field("precip").textContent = chance ? `Precipitation ${chance}%${mm ? `, ${mm} mm` : ""}` : "Dry";
    field("wind").textContent = `Wind ${Math.round(d.wind_speed_10m_max[i] || 0)} m/s`;

    const h = data.hourly || {};
    const strip = field("hours");
    strip.replaceChildren();
    (h.time || []).forEach((t, j) => {
      const at = Number(t.slice(11, 13));
      if (t.slice(0, 10) !== today || !hours.includes(at) || at <= hour || h.temperature_2m[j] == null) return;
      const li = el("li", "weather-hour");
      li.append(el("span", "weather-time", t.slice(11, 16)), el("span", "weather-hour-temp", deg(h.temperature_2m[j])),
        el("span", "weather-hour-cond", condition(h.weather_code[j])));
      strip.append(li);
    });
    strip.hidden = !strip.children.length;

    const list = field("days");
    list.replaceChildren();
    d.time.forEach((date, j) => {
      if (date <= today || d.temperature_2m_max[j] == null || list.children.length >= days) return;
      const li = el("li", "weather-day");
      const temps = el("span", "weather-day-temps", `${deg(d.temperature_2m_max[j])} `);
      const low = el("span", "weather-low");
      low.append(el("span", "visually-hidden", "low "), deg(d.temperature_2m_min[j]));
      temps.append(low);
      li.append(el("span", "weather-day-name", weekday(date)), el("span", "weather-day-cond", condition(d.weather_code[j])), temps);
      list.append(li);
    });
    list.hidden = !list.children.length;

    const sun = field("sun");
    sun.replaceChildren();
    const rise = (d.sunrise[i] || "").slice(11, 16), set = (d.sunset[i] || "").slice(11, 16);
    if (rise && set) sun.append(el("span", "", `Sunrise ${rise}`), sep(), el("span", "", `Sunset ${set}`));
    sun.hidden = !sun.children.length;
    body.hidden = false;
  }

  async function forecast(where) {
    const lat = round(where.lat), lon = round(where.lon);
    const cached = read(CACHE);
    if (cached && cached.lat === lat && cached.lon === lon && Date.now() - cached.at < FRESH_MS) return cached.data;
    const params = new URLSearchParams({
      latitude: String(lat), longitude: String(lon), timezone: "auto", current: "temperature_2m",
      daily: DAILY.join(","), hourly: HOURLY.join(","), forecast_days: String(days + 1), wind_speed_unit: "ms",
    });
    const res = await fetch(`${API}?${params}`);
    const data = await res.json();
    if (!res.ok || data.error) throw new Error(data.reason || `HTTP ${res.status}`);
    write(CACHE, { lat, lon, at: Date.now(), data });
    return data;
  }

  let shown = null;                               // the place now in the box
  async function show(where, note = "") {
    say(note || "Loading the forecast…");
    let data = null;
    try { data = await forecast(where); } catch { /* below */ }
    label(where);
    try {
      if (!data) throw new Error("no data");
      render(data);
      shown = where;
      say(note);
    } catch {
      body.hidden = true;
      say("The forecast isn't available right now.");
    }
  }

  function locate() {
    return new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ place: "", lat: pos.coords.latitude, lon: pos.coords.longitude, accuracy: pos.coords.accuracy,
        here: true }), reject,
      { enableHighAccuracy: false, maximumAge: FRESH_MS, timeout: 15000 }));
  }

  async function useHere() {
    say("Finding your location…");
    try {
      const where = await locate();
      write(WHERE, "here");
      await show(where);
      try {
        Object.assign(where, await placeName(where));
        if (shown === where) label(where);
      } catch { /* the coordinates still show */ }
    } catch (err) {
      write(WHERE, null);
      const why = err && err.code === 1 ? "Location permission was not given" : "Couldn't find your location";
      await show(home, `${why}, so this is ${home.place}.`);
    }
  }

  toggle.addEventListener("click", () => {
    if (shown && shown.here) { write(WHERE, null); show(home); }
    else useHere();
  });

  async function permitted() {
    try { return (await navigator.permissions.query({ name: "geolocation" })).state === "granted"; } catch { return false; }
  }

  box.hidden = false;
  (async () => {
    // Only ask the browser for the position on page load when the reader chose it before and the
    // permission still stands, so the page never opens with a permission prompt
    if (canLocate && read(WHERE) === "here" && await permitted()) useHere();
    else show(home);
  })();
})();
