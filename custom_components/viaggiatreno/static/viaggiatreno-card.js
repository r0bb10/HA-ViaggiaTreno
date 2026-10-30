/* ViaggiaTreno card — no runtime dependencies, external scripts, or API polling. */
const VERSION = "2026.10.1";
const MODES = ["arrivals", "departures", "combined"];
const CATEGORY_ICONS = /^\/(?:viaggiatreno\/static\/categories)\/(?:reg|rv|re|s|ic|icn|ec|en|fr|fa|fb)\.svg$/;
const TEXT = {
  it: {
    arrivals: "Arrivi", departures: "Partenze", combined: "Monitor unico",
    operator: "Vettore", category: "Categoria", scheduled: "Orario", train: "Treno",
    origin: "Origine", destination: "Destinazione", delay: "Ritardo", platform: "Binario",
    updated: "Aggiornato", refresh: "Aggiorna", noTrains: "Nessun treno nel periodo disponibile",
    missing: "Seleziona le entità ViaggiaTreno nell’editor della scheda.",
    unavailable: "Collegamento non disponibile · ultimi dati ricevuti",
    mismatch: "Le entità selezionate appartengono a stazioni diverse.",
    planned: "* Binario programmato, non ancora confermato", cancelled: "SOPPRESSO",
    fallback: "Orario di partenza per i treni senza arrivo abbinato",
    count: "treni", unknown: "Non disponibile", failed: "Aggiornamento non riuscito",
    masthead: "MONITOR ARRIVI & PARTENZE", source: "Dati",
    close: "Chiudi", loading: "Caricamento…", at: "alle", lastReport: "Ultimo rilevamento",
    station: "Stazione", arrivalEntity: "Entità arrivi", departureEntity: "Entità partenze",
    mode: "Vista iniziale", rows: "Numero massimo di treni", title: "Titolo (facoltativo)",
    language: "Lingua", tabs: "Mostra selettore delle viste", compact: "Righe compatte",
  },
  en: {
    arrivals: "Arrivals", departures: "Departures", combined: "Combined monitor",
    operator: "Operator", category: "Category", scheduled: "Scheduled", train: "Train",
    origin: "Origin", destination: "Destination", delay: "Delay", platform: "Platform",
    updated: "Updated", refresh: "Refresh", noTrains: "No trains in the available time window",
    missing: "Select the ViaggiaTreno entities in the card editor.",
    unavailable: "Connection unavailable · showing the last received data",
    mismatch: "The selected entities belong to different stations.",
    planned: "* Planned platform, not yet confirmed", cancelled: "CANCELLED",
    fallback: "Departure time for services without a matching arrival",
    count: "trains", unknown: "Unavailable", failed: "Refresh failed",
    masthead: "ARRIVALS & DEPARTURES MONITOR", source: "Data",
    close: "Close", loading: "Loading…", at: "at", lastReport: "Last reported location",
    station: "Station", arrivalEntity: "Arrivals entity", departureEntity: "Departures entity",
    mode: "Initial view", rows: "Maximum trains", title: "Title (optional)",
    language: "Language", tabs: "Show view selector", compact: "Compact rows",
  },
};

const STYLE = `
  :host { display:block; min-width:0; color-scheme:inherit;
    --vt-yellow:#fdd701; --vt-pale:#fee581; --vt-grey:#565655;
    --vt-surface:var(--ha-card-background,var(--card-background-color,#fff));
    --vt-ink:var(--primary-text-color,#333); --vt-muted:var(--secondary-text-color,#656565);
    --vt-border:var(--divider-color,#d5d5d5); --vt-secondary:var(--secondary-background-color,#eee); }
  * { box-sizing:border-box; }
  ha-card { display:block; overflow:hidden; background:var(--vt-surface); color:var(--vt-ink); font-family:Arial,Helvetica,sans-serif;
    border-radius:8px; border:1px solid var(--vt-border); box-shadow:none; }
  .top { padding:24px 26px 0; }
  .masthead { display:flex; align-items:center; justify-content:space-between; gap:16px; }
  .eyebrow { font-size:13px; font-weight:700; letter-spacing:.06em; line-height:1.5; }
  .live { font-style:italic; color:var(--vt-muted); margin-left:7px; font-weight:400; }
  .brand { display:block; width:180px; max-width:40%; height:auto; flex-shrink:0; object-fit:contain; }
  .station { font-size:clamp(24px,3vw,36px); line-height:1.2; font-weight:800; margin:20px 0 16px;
    letter-spacing:.025em; overflow-wrap:anywhere; }
  button { font:inherit; cursor:pointer; }
  button:focus-visible, .scroll:focus-visible { outline:3px solid var(--primary-color,#007d79); outline-offset:-3px; }
  .updated { font-size:12px; color:var(--vt-muted); padding:12px 0 14px; display:flex; gap:8px; flex-wrap:wrap;
    align-items:center; justify-content:flex-end; text-align:right; line-height:1.5; }
  .updated .divider { color:var(--vt-border); }
  .notice { background:var(--vt-surface); background:color-mix(in srgb,var(--vt-surface) 85%,var(--vt-yellow));
    color:var(--vt-ink); border-top:1px solid var(--vt-border); padding:10px 26px; font-size:13px; }
  .scroll { overflow:auto; scrollbar-width:thin; scrollbar-color:var(--vt-muted) var(--vt-secondary); }
  table { width:100%; border-collapse:collapse; min-width:960px; table-layout:fixed; }
  caption { text-align:left; padding:0; }
  th { background:var(--vt-yellow); color:#333; text-align:left; padding:13px 12px;
    font-size:13px; font-weight:700; position:sticky; top:0; z-index:1; }
  th:first-child, td:first-child { padding-left:26px; }
  th:last-child, td:last-child { padding-right:22px; }
  td { padding:13px 12px; height:62px; vertical-align:middle; border-bottom:3px solid var(--vt-surface);
    font-size:16px; font-weight:500; overflow-wrap:anywhere; }
  tr.yellow { background:var(--vt-pale); color:var(--vt-grey); }
  tr.grey { background:var(--vt-grey); color:var(--vt-pale); }
  .time, .number, .delay, .platform { font-variant-numeric:tabular-nums; white-space:nowrap; }
  .time, .number { font-weight:700; font-size:18px; }
  .place { font-size:14px; font-weight:700; line-height:1.35; }
  .delay { font-weight:700; }
  .platform { font-size:21px; font-weight:800; }
  .platform sup { font-size:12px; margin-left:2px; }
  .asset { display:block; max-width:100%; object-fit:contain; object-position:left center; }
  .operator-image { width:106px; height:30px; }
  .category-image { width:47px; height:30px; }
  tr.yellow .operator-image, tr.yellow .category-image[data-original] { filter:brightness(0) opacity(.72); }
  tr.grey .operator-image, tr.grey .category-image[data-original] { filter:brightness(0) invert(1); }
  .fallback { font-size:12px; font-weight:700; }
  .category-badge { display:inline-block; border:1px solid currentColor; border-radius:3px; padding:3px 5px; font-size:12px; font-weight:700; }
  .cancelled .time, .cancelled .place { text-decoration:line-through; }
  .cancel-label { font-size:10px; letter-spacing:.02em; white-space:normal; }
  .empty { padding:35px 24px; font-size:15px; text-align:center; background:var(--vt-secondary); color:var(--vt-muted); }
  .compact td { padding-top:7px; padding-bottom:7px; height:46px; }
  .compact .place { font-size:13px; }
  .compact .time, .compact .number { font-size:16px; }
  tbody tr { cursor:pointer; }
  tbody tr:focus-visible { outline:3px solid var(--primary-color,#007d79); outline-offset:-3px; }
  dialog { position:fixed; margin:0; padding:0; width:max-content; max-width:calc(100vw - 32px);
    max-height:calc(100dvh - 32px); overflow:auto; overflow-wrap:anywhere; border:1px solid var(--vt-border);
    border-top:5px solid var(--vt-yellow); border-radius:8px; background:var(--vt-surface);
    color:var(--vt-ink); box-shadow:0 12px 48px #0006; font-family:Arial,Helvetica,sans-serif; }
  dialog::backdrop { background:#0008; }
  .popup-content { padding:24px; text-align:center; }
  .popup-report { flex:1; font-size:18px; font-weight:700; line-height:1.5; }
  .sr { position:absolute; width:1px; height:1px; padding:0; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
  @media(max-width:600px) {
    .top { padding:17px 16px 0; } .station { margin-top:16px; font-size:26px; }
    .eyebrow { font-size:11px; } .brand { width:130px; } .updated { font-size:11px; }
    th:first-child, td:first-child { padding-left:16px; } .notice { padding-left:16px; padding-right:16px; }
    table { min-width:960px; } td { height:56px; }
  }
`;

function element(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (value !== undefined && value !== null) node.setAttribute(name, String(value));
  }
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function isBoard(state, direction) {
  return state?.entity_id?.startsWith("sensor.") && state.attributes?.direction === direction
    && typeof state.attributes?.station_id === "string";
}

function discover(hass) {
  const states = Object.values(hass?.states || {});
  const arrivals = states.find((state) => isBoard(state, "arrivi"));
  const departures = states.find((state) => isBoard(state, "partenze")
    && (!arrivals || state.attributes.station_id === arrivals.attributes.station_id));
  return { arrivals_entity: arrivals?.entity_id || "", departures_entity: departures?.entity_id || "" };
}

function safeIcon(path) {
  // Train data is remote. Only permit the integration's locally bundled icons.
  return typeof path === "string"
    && /^\/viaggiatreno\/static\/(operators|categories)\/[a-z0-9_-]+\.svg$/.test(path)
    ? path : null;
}

export function trainRows(arrivals = [], departures = [], mode = "arrivals") {
  arrivals = arrivals.filter((row) => row && typeof row === "object");
  departures = departures.filter((row) => row && typeof row === "object");
  // The shared upstream board DTO calls this flag "arrivato" for both
  // directions. In arrivals it means the station arrival is completed; in
  // departures it means the station departure is completed. It is not a
  // statement that the train has reached its final destination.
  const completed = (row) => row.arrived === true;
  let rows;
  if (mode === "departures") rows = departures.filter((row) => !completed(row));
  else if (mode === "arrivals") rows = arrivals.filter((row) => !completed(row));
  else {
    const departuresByService = new Map();
    for (const row of departures) {
      if (!row.service_id) continue;
      const matches = departuresByService.get(row.service_id) || [];
      matches.push(row);
      departuresByService.set(row.service_id, matches);
    }
    const activeArrivals = arrivals.filter((row) => {
      const matches = row.service_id && departuresByService.get(row.service_id);
      // Keep a train during its station dwell, even if the arrival is complete.
      // Once its departure is complete, remove the merged service as a whole.
      return matches?.length ? !matches.every(completed) : !completed(row);
    });
    const keys = new Set(arrivals.map((row) => row.service_id).filter(Boolean));
    rows = [...activeArrivals, ...departures.filter((row) => !completed(row)
      && (!row.service_id || !keys.has(row.service_id)))];
  }
  return rows.filter((row) => row && typeof row === "object")
    .sort((a, b) => String(a.scheduled || "9999").localeCompare(String(b.scheduled || "9999"))
      || String(a.train_number).localeCompare(String(b.train_number), undefined, { numeric: true }));
}

export class ViaggiaTrenoCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._mode = "arrivals";
  }

  static getConfigElement() { return document.createElement("viaggiatreno-card-editor"); }
  static getStubConfig(hass) {
    const entities = discover(hass);
    return { ...entities, mode: entities.arrivals_entity ? "arrivals" : "departures", max_rows: 12, language: "it" };
  }

  setConfig(config) {
    const mode = config.mode || (config.arrivals_entity ? "arrivals" : "departures");
    if (!MODES.includes(mode)) throw new Error("mode: arrivals, departures, combined");
    if (!config.arrivals_entity && !config.departures_entity) {
      throw new Error("Select an arrivals_entity or departures_entity");
    }
    const maxRows = Number(config.max_rows ?? 12);
    if (!Number.isInteger(maxRows) || maxRows < 1 || maxRows > 100) {
      throw new Error("max_rows must be an integer between 1 and 100");
    }
    if (!["it", "en", "auto"].includes(config.language || "it")) {
      throw new Error("language: it, en, auto");
    }
    this._config = { compact: false, language: "it", ...config, mode, max_rows: maxRows };
    this._mode = mode;
    this._render();
  }

  set hass(hass) {
    const previous = this._hass;
    this._hass = hass;
    if (!this._config) return;
    const changed = [this._config.arrivals_entity, this._config.departures_entity]
      .some((id) => previous?.states[id] !== hass.states[id]);
    if (!previous || changed || previous.language !== hass.language || previous.locale !== hass.locale) this._render();
  }

  getCardSize() { return 4 + Math.min(this._config?.max_rows || 12, 12); }
  getGridOptions() { return { columns: 12, min_columns: 6, rows: "auto" }; }

  _locale() {
    return this._config.language === "auto"
      ? (this._hass?.language?.startsWith("it") ? "it" : "en") : this._config.language;
  }

  _time(value, full = false) {
    if (!value || !Number.isFinite(new Date(value).getTime())) return "—";
    const options = full
      ? { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }
      : { hour: "2-digit", minute: "2-digit", hour12: false };
    return new Intl.DateTimeFormat(this._locale() === "it" ? "it-IT" : "en-GB", {
      ...options, timeZone: this._hass?.config?.time_zone || "Europe/Rome",
    }).format(new Date(value));
  }

  _imageCell(train, type) {
    const cell = element("td");
    const label = train[type] || train[`${type}_code`] || "—";
    const fallback = element("span", { class: "fallback" }, label);
    const path = safeIcon(train[`${type}_icon`]);
    if (type === "category" && (!path || !CATEGORY_ICONS.test(path))) {
      cell.append(element("span", { class: "category-badge" }, train.category_code || label));
      return cell;
    }
    if (path && !path.endsWith("/unknown.svg")) {
      const image = element("img", { src: path, alt: label, title: label, class: `asset ${type}-image`, loading: "lazy" });
      if (type === "category" && CATEGORY_ICONS.test(path) && !path.endsWith('/s.svg')) image.setAttribute("data-original", "true");
      image.addEventListener("error", () => image.replaceWith(fallback), { once: true });
      cell.append(image);
    } else cell.append(fallback);
    return cell;
  }

  disconnectedCallback() {
    this.shadowRoot.querySelector('dialog')?.close();
  }

  async _showReport(train, stationId, trigger, event) {
    if (this.shadowRoot.querySelector('dialog')) return;
    const t = TEXT[this._locale()];
    const dialog = element('dialog', { 'aria-label': t.lastReport, tabindex: '-1' });
    const content = element('div', { class: 'popup-content' });
    const report = element('span', { class: 'popup-report', role: 'status' }, t.loading);
    const bounds = trigger.getBoundingClientRect();
    const pointer = event && (event.detail > 0 || event.clientX || event.clientY);
    // Capture the activation point once; pointer movement never moves the popup.
    const anchor = pointer ? { x: event.clientX, y: event.clientY }
      : { x: bounds.left + bounds.width / 2, y: bounds.bottom };
    const position = () => {
      if (!dialog.open) return;
      const viewport = window.visualViewport;
      const left = (viewport?.offsetLeft || 0) + 16;
      const top = (viewport?.offsetTop || 0) + 16;
      const right = left + (viewport?.width || window.innerWidth) - 32;
      const bottom = top + (viewport?.height || window.innerHeight) - 32;
      const { width, height } = dialog.getBoundingClientRect();
      const x = anchor.x + 12 + width <= right ? anchor.x + 12 : anchor.x - width - 12;
      const y = anchor.y + 12 + height <= bottom ? anchor.y + 12 : anchor.y - height - 12;
      dialog.style.left = `${Math.max(left, Math.min(x, right - width))}px`;
      dialog.style.top = `${Math.max(top, Math.min(y, bottom - height))}px`;
    };
    dialog.addEventListener('click', (event) => {
      const bounds = dialog.getBoundingClientRect();
      if (event.target === dialog && (event.clientX < bounds.left || event.clientX > bounds.right
        || event.clientY < bounds.top || event.clientY > bounds.bottom)) dialog.close();
    });
    dialog.addEventListener('close', () => {
      window.removeEventListener('resize', position);
      window.visualViewport?.removeEventListener('resize', position);
      dialog.remove();
      const target = trigger.isConnected ? trigger : [...this.shadowRoot.querySelectorAll('tbody tr')]
        .find((row) => row.dataset.serviceId === train.service_id);
      target?.focus({ preventScroll: true });
    }, { once: true });
    content.append(report);
    dialog.append(content);
    this.shadowRoot.append(dialog);
    dialog.showModal();
    position();
    window.addEventListener('resize', position);
    window.visualViewport?.addEventListener('resize', position);
    try {
      if (!train.service_id) throw new Error('Missing service identity');
      const result = await this._hass.callWS({ type: 'viaggiatreno/last_report',
        station_id: stationId, service_id: train.service_id });
      const time = this._time(result.timestamp);
      report.textContent = result.station && time !== '—'
        ? `${result.station} ${t.at} ${time}` : t.unknown;
    } catch {
      report.textContent = t.unknown;
    }
    position();
  }

  _render() {
    if (!this._config || !this._hass) return;
    const config = this._config;
    const t = TEXT[this._locale()];
    const arrival = this._hass.states[config.arrivals_entity];
    const departure = this._hass.states[config.departures_entity];
    const selected = this._mode === "departures" ? departure : arrival || departure;
    const mismatch = arrival && departure && arrival.attributes.station_id !== departure.attributes.station_id;
    const relevant = this._mode === "combined" ? [arrival, departure]
      : [this._mode === "arrivals" ? arrival : departure];
    const missing = relevant.some((state) => !state);
    const unavailable = relevant.some((state) => state && ["unavailable", "unknown"].includes(state.state));
    const list = (state) => Array.isArray(state?.attributes.trains) ? state.attributes.trains : [];
    const allRows = mismatch || missing ? [] : trainRows(list(arrival), list(departure), this._mode);
    const rows = allRows.slice(0, config.max_rows);
    const card = element("ha-card", { class: config.compact ? "compact" : "" });
    const top = element("header", { class: "top" });
    const masthead = element("div", { class: "masthead" });
    const eyebrow = element("div", { class: "eyebrow" }, t.masthead);
    eyebrow.append(element("span", { class: "live" }, "LIVE"));
    masthead.append(eyebrow, element("img", { class: "brand", src: "/viaggiatreno/brand/logo@2x.png", alt: "ViaggiaTreno" }));
    top.append(masthead, element("h2", { class: "station" }, config.title || selected?.attributes.station_name || t.station));
    const updated = element("div", { class: "updated", "aria-live": "polite" });
    const timestamps = relevant.map((s) => s?.attributes.last_refresh).filter(Boolean).sort();
    updated.append(element("span", {}, `${t.updated}: ${this._time(timestamps[0], true)}`));
    top.append(updated);
    card.append(top);
    if (mismatch || missing || unavailable) {
      const message = mismatch ? t.mismatch : missing ? t.missing : t.unavailable;
      card.append(element("div", { class: "notice", role: "status" }, message));
    }
    const scroll = element("div", { class: "scroll", tabindex: "0", role: "region", "aria-label": `${selected?.attributes.station_name || t.station} · ${t[this._mode]}` });
    const table = element("table");
    table.append(element("caption", { class: "sr" }, `${t[this._mode]} · ${selected?.attributes.station_name || t.station}`));
    const colgroup = element("colgroup");
    for (const width of ["13%", "8%", "9%", "9%", "21%", "21%", "10%", "9%"]) colgroup.append(element("col", { style: `width:${width}` }));
    table.append(colgroup);
    const head = element("thead");
    const headerRow = element("tr");
    for (const key of ["operator", "category", "scheduled", "train", "origin", "destination", "delay", "platform"]) {
      headerRow.append(element("th", { scope: "col" }, t[key]));
    }
    head.append(headerRow);
    const body = element("tbody");
    for (const [index, train] of rows.entries()) {
      const row = element("tr", { class: `${index % 2 ? "grey" : "yellow"}${train.cancelled ? " cancelled" : ""}`,
        tabindex: '0', 'aria-label': `${train.train_number} · ${t.lastReport}`, 'aria-haspopup': 'dialog',
        'data-service-id': train.service_id });
      const openReport = (event) => this._showReport(train, selected?.attributes.station_id, row, event);
      row.addEventListener('click', openReport);
      row.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openReport(); }
      });
      row.append(this._imageCell(train, "operator"), this._imageCell(train, "category"),
        element("td", { class: "time" }, this._time(train.scheduled)),
        element("td", { class: "number" }, train.train_number || "—"),
        element("td", { class: "place", title: train.origin || t.unknown }, train.origin || "—"),
        element("td", { class: "place", title: train.destination || t.unknown }, train.destination || "—"));
      const delay = Number.isFinite(train.delay) ? train.delay : null;
      const delayText = train.cancelled ? t.cancelled : delay === null ? "—" : delay === 0 ? "0" : `${delay > 0 ? "+" : "−"}${Math.abs(delay)}′`;
      row.append(element("td", { class: `delay${train.cancelled ? " cancel-label" : ""}` }, delayText));
      const platform = element("td", { class: "platform", title: train.platform_source === "planned" ? t.planned.slice(2) : t.platform }, train.platform || "—");
      if (train.platform && train.platform_source === "planned") platform.append(element("sup", {}, "*"));
      row.append(platform);
      body.append(row);
    }
    table.append(head, body);
    scroll.append(table);
    card.append(scroll);
    if (!rows.length) card.append(element("div", { class: "empty" }, missing ? t.missing : mismatch ? t.mismatch : unavailable ? t.unavailable : t.noTrains));
    // Keep the scroll position across state updates and local view switches.
    const scrollLeft = this.shadowRoot.querySelector(".scroll")?.scrollLeft || 0;
    const style = element("style", {}, STYLE);
    const previousCard = this.shadowRoot.querySelector('ha-card');
    if (previousCard) previousCard.replaceWith(card);
    else this.shadowRoot.replaceChildren(style, card);
    scroll.scrollLeft = scrollLeft;
  }
}

export class ViaggiaTrenoCardEditor extends HTMLElement {
  constructor() { super(); this.attachShadow({ mode: "open" }); }
  setConfig(config) { this._config = { mode: "arrivals", max_rows: 12, language: "it", ...config }; this._render(); }
  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._render();
  }
  _change(key, value) {
    const config = { ...this._config, [key]: value };
    if (value === "") delete config[key];
    if (["arrivals_entity", "departures_entity"].includes(key) && value && this._hass) {
      const station = this._hass.states[value]?.attributes.station_id;
      const otherKey = key === "arrivals_entity" ? "departures_entity" : "arrivals_entity";
      const direction = key === "arrivals_entity" ? "partenze" : "arrivi";
      const other = Object.values(this._hass.states).find((state) => isBoard(state, direction) && state.attributes.station_id === station);
      if (other) config[otherKey] = other.entity_id;
      else delete config[otherKey];
    }
    this._config = config;
    this.dispatchEvent(new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true }));
    this._render();
  }
  _render() {
    if (!this._config || !this._hass) return;
    const t = TEXT[this._config.language === "en" ? "en" : "it"];
    const root = element("div", { class: "fields" });
    const field = (label, input) => {
      const wrapper = element("label");
      wrapper.append(element("span", {}, label), input);
      root.append(wrapper);
    };
    for (const [key, direction, label] of [["arrivals_entity", "arrivi", t.arrivalEntity], ["departures_entity", "partenze", t.departureEntity]]) {
      const select = element("select", { "aria-label": label });
      select.append(element("option", { value: "" }, "—"));
      const options = Object.values(this._hass.states).filter((state) => isBoard(state, direction));
      for (const state of options) select.append(element("option", { value: state.entity_id }, `${state.attributes.friendly_name || state.entity_id} (${state.entity_id})`));
      if (this._config[key] && !options.some((state) => state.entity_id === this._config[key])) select.append(element("option", { value: this._config[key] }, this._config[key]));
      select.value = this._config[key] || "";
      select.addEventListener("change", () => this._change(key, select.value));
      field(label, select);
    }
    for (const [key, label, options] of [
      ["mode", t.mode, MODES.map((mode) => [mode, t[mode]])],
      ["language", t.language, [["it", "Italiano"], ["en", "English"], ["auto", "Home Assistant"]]],
    ]) {
      const select = element("select", { "aria-label": label });
      for (const [value, text] of options) select.append(element("option", { value }, text));
      select.value = this._config[key];
      select.addEventListener("change", () => this._change(key, select.value));
      field(label, select);
    }
    for (const [key, label, type] of [["title", t.title, "text"], ["max_rows", t.rows, "number"]]) {
      const input = element("input", { type, "aria-label": label });
      input.value = this._config[key] ?? "";
      if (type === "number") { input.min = "1"; input.max = "100"; input.step = "1"; }
      input.addEventListener("change", () => {
        if (input.checkValidity()) this._change(key, type === "number" ? Number(input.value) : input.value);
      });
      field(label, input);
    }
    for (const [key, label] of [["compact", t.compact]]) {
      const input = element("input", { type: "checkbox", "aria-label": label });
      input.checked = Boolean(this._config[key]);
      input.addEventListener("change", () => this._change(key, input.checked));
      field(label, input);
    }
    const style = element("style", {}, `:host{display:block}.fields{display:grid;gap:16px;padding:8px 0}label{display:grid;gap:6px;font:inherit;color:var(--primary-text-color)}select,input:not([type=checkbox]){box-sizing:border-box;width:100%;padding:12px;border:1px solid var(--divider-color,#aaa);border-radius:4px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#222);font:inherit}input[type=checkbox]{justify-self:start;width:20px;height:20px;accent-color:#007d79}`);
    this.shadowRoot.replaceChildren(style, root);
  }
}

if (!customElements.get("viaggiatreno-card")) customElements.define("viaggiatreno-card", ViaggiaTrenoCard);
if (!customElements.get("viaggiatreno-card-editor")) customElements.define("viaggiatreno-card-editor", ViaggiaTrenoCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "viaggiatreno-card")) {
  window.customCards.push({ type: "viaggiatreno-card", name: "ViaggiaTreno", preview: true,
    description: "Tabellone ferroviario in stile RFI: arrivi, partenze e monitor unico." });
}
console.info(`%c VIAGGIATRENO %c ${VERSION} `, "background:#fdd701;color:#333;font-weight:bold", "background:#565655;color:#fee581");
