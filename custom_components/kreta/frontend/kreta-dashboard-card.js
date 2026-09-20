const KRETA_VIEWS = ["overview", "today", "tomorrow", "week", "grades", "tests", "homework", "changes", "absences", "school_year"];
const KRETA_BOOLEAN_OPTIONS = ["show_school_name", "show_teacher", "show_room", "show_lesson_number", "show_time", "show_progress", "show_next_lesson", "show_tests", "show_homework", "show_substitutions", "show_cancelled", "show_grade_statistics", "show_absences", "show_messages", "compact", "dense", "hide_empty_sections", "use_24_hour", "use_theme_color"];
const KRETA_DEFAULTS = {view: "overview", show_school_name: true, show_teacher: true, show_room: true, show_lesson_number: true, show_time: true, show_progress: true, show_next_lesson: true, show_tests: true, show_homework: true, show_substitutions: true, show_cancelled: true, show_grade_statistics: true, show_absences: true, show_messages: true, compact: false, dense: false, days_to_show: 5, recent_grades: 10, upcoming_tests: 10, homework_entries: 10, first_lesson: 0, last_lesson: 10, hide_empty_sections: true, use_24_hour: true, use_theme_color: true, card_height: "auto", week_layout: "columns", mobile_layout: "scroll"};
const KRETA_TEXT = {
  hu: {overview: "Áttekintés", today: "Ma", tomorrow: "Holnap", week: "Hét", grades: "Jegyek", tests: "Dolgozatok", homework: "Házi feladat", changes: "Változások", absences: "Hiányzások", school_year: "Tanév", current: "Jelenlegi óra", next: "Következő", noSchool: "Nincs tanítás", empty: "Nincs megjeleníthető adat", loading: "KRÉTA-adatok betöltése…", error: "A KRÉTA-adatok átmenetileg nem érhetők el", partial: "Néhány KRÉTA-adat átmenetileg nem érhető el", remaining: "perc van hátra", total: "Összesen", lastUpdate: "Utolsó frissítés"},
  en: {overview: "Overview", today: "Today", tomorrow: "Tomorrow", week: "Week", grades: "Grades", tests: "Tests", homework: "Homework", changes: "Changes", absences: "Absences", school_year: "School year", current: "Current lesson", next: "Next", noSchool: "No school", empty: "No data to display", loading: "Loading KRÉTA data…", error: "KRÉTA data is temporarily unavailable", partial: "Some KRÉTA data is temporarily unavailable", remaining: "minutes remaining", total: "Total", lastUpdate: "Last update"}
};

function kretaNode(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

function kretaTime(value, language, use24Hour) {
  if (!value) return "";
  return new Intl.DateTimeFormat(language, {hour: "2-digit", minute: "2-digit", hour12: !use24Hour}).format(new Date(value));
}

class KretaDashboardCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._request = 0;
    this._timer = window.setInterval(() => this._render(), 30000);
  }

  disconnectedCallback() {
    window.clearInterval(this._timer);
  }

  static getConfigElement() {
    return document.createElement("kreta-dashboard-card-editor");
  }

  static getStubConfig() {
    return {type: "custom:kreta-dashboard-card", ...KRETA_DEFAULTS};
  }

  setConfig(config) {
    if (!config.entry_id) throw new Error("entry_id is required");
    this._config = {...KRETA_DEFAULTS, ...config};
    this._load();
  }

  set hass(value) {
    this._hass = value;
    this._language = value.language === "hu" ? "hu" : "en";
    if (this._config && !this._loadedFor) this._load();
  }

  getCardSize() {
    return this._config?.view === "week" ? 8 : 6;
  }

  async _load() {
    if (!this._hass || !this._config) return;
    const request = ++this._request;
    this._loading = true;
    this._error = false;
    this._render();
    const view = this._config.view;
    let command = "overview";
    const payload = {entry_id: this._config.entry_id};
    const now = new Date();
    if (view === "today" || view === "tomorrow") {
      command = "day";
      if (view === "tomorrow") now.setDate(now.getDate() + 1);
      payload.date = now.toISOString().slice(0, 10);
    } else if (view === "week") {
      command = "week";
      payload.date = now.toISOString().slice(0, 10);
    } else if (["grades", "tests", "homework", "changes", "absences", "school_year"].includes(view)) {
      command = view;
      if (["grades", "tests", "homework", "absences"].includes(view)) payload.limit = this._limitFor(view);
    }
    try {
      const data = await this._hass.callWS({type: `kreta/get_${command}`, ...payload});
      if (request !== this._request) return;
      this._data = data;
      this._loadedFor = `${view}:${this._config.entry_id}`;
    } catch (error) {
      if (request !== this._request) return;
      this._error = true;
    } finally {
      if (request === this._request) {
        this._loading = false;
        this._render();
      }
    }
  }

  _limitFor(view) {
    if (view === "grades") return this._config.recent_grades;
    if (view === "tests") return this._config.upcoming_tests;
    if (view === "homework") return this._config.homework_entries;
    return 50;
  }

  _style() {
    const style = kretaNode("style");
    style.textContent = `
      :host{display:block}.card{height:var(--kreta-height,auto);overflow:auto;color:var(--primary-text-color);background:var(--ha-card-background,var(--card-background-color));border-radius:var(--ha-card-border-radius,12px);box-shadow:var(--ha-card-box-shadow);font-family:var(--paper-font-body1_-_font-family,inherit)}
      .wrap{padding:18px;display:grid;gap:16px}.dense .wrap{padding:12px;gap:10px}.head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.title{font-size:22px;font-weight:650}.muted{color:var(--secondary-text-color);font-size:13px}.status{width:9px;height:9px;border-radius:50%;background:var(--success-color,#43a047);display:inline-block;margin-right:6px}.status.partial{background:var(--warning-color,#ffa000)}
      nav{display:flex;gap:6px;overflow:auto;padding-bottom:2px}button{min-height:44px;border:0;border-radius:10px;padding:0 13px;background:var(--secondary-background-color);color:var(--primary-text-color);cursor:pointer;white-space:nowrap}button.active{background:var(--kreta-accent,var(--primary-color));color:var(--text-primary-color,#fff)}button:focus-visible,.lesson:focus-visible{outline:2px solid var(--kreta-accent,var(--primary-color));outline-offset:2px}
      .hero{padding:18px;border-radius:14px;background:color-mix(in srgb,var(--kreta-accent,var(--primary-color)) 12%,var(--card-background-color));display:grid;gap:7px}.hero h2{margin:0;font-size:25px}.heroRow{display:flex;gap:14px;flex-wrap:wrap}.progress{height:7px;background:var(--divider-color);border-radius:8px;overflow:hidden}.bar{height:100%;background:var(--kreta-accent,var(--primary-color));transition:width .25s ease}
      .section{display:grid;gap:9px}.section h3{margin:0;font-size:16px}.lesson,.row{display:grid;grid-template-columns:64px minmax(100px,1fr) auto;gap:12px;align-items:center;padding:11px;border:1px solid var(--divider-color);border-radius:11px;min-height:44px}.lesson.cancelled{opacity:.65;text-decoration:line-through}.subject{font-weight:600}.meta{font-size:13px;color:var(--secondary-text-color)}.badges{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}.badge{border-radius:10px;padding:2px 7px;font-size:11px;background:var(--secondary-background-color)}
      .week{display:grid;grid-template-columns:repeat(5,minmax(190px,1fr));gap:10px;overflow:auto}.day{display:grid;align-content:start;gap:8px;min-width:190px}.day h3{position:sticky;top:0;background:var(--card-background-color);padding:6px 0;z-index:1}.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:9px}.stat{padding:12px;border-radius:10px;background:var(--secondary-background-color)}.stat strong{display:block;font-size:20px}.empty,.error,.loading{padding:34px;text-align:center;color:var(--secondary-text-color)}
      @media(max-width:700px){.wrap{padding:14px}.title{font-size:19px}.week{grid-template-columns:repeat(5,82vw)}.lesson,.row{grid-template-columns:54px 1fr}.badges{grid-column:2;justify-content:flex-start}.hero{padding:15px}}
    `;
    return style;
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const card = kretaNode("ha-card", `card${this._config.dense ? " dense" : ""}`);
    card.style.setProperty("--kreta-height", this._config.card_height || "auto");
    if (!this._config.use_theme_color && this._config.accent_color) card.style.setProperty("--kreta-accent", this._config.accent_color);
    const wrap = kretaNode("div", "wrap");
    wrap.append(this._header(), this._navigation());
    if (this._loading && !this._data) wrap.append(kretaNode("div", "loading", this._text("loading")));
    else if (this._error) wrap.append(kretaNode("div", "error", this._text("error")));
    else if (this._data) wrap.append(this._content());
    card.append(wrap);
    this.shadowRoot.replaceChildren(this._style(), card);
  }

  _header() {
    const head = kretaNode("div", "head");
    const left = kretaNode("div");
    const school = this._data?.profile?.school_name;
    left.append(kretaNode("div", "title", this._config.title || (this._config.show_school_name && school) || "KRÉTA"));
    if (this._data?.last_update) left.append(kretaNode("div", "muted", `${this._text("lastUpdate")}: ${new Date(this._data.last_update).toLocaleString(this._language)}`));
    const status = kretaNode("div", "muted");
    status.append(kretaNode("span", `status${this._data?.status === "partial_data" ? " partial" : ""}`), document.createTextNode(this._data?.status === "partial_data" ? this._text("partial") : "KRÉTA"));
    head.append(left, status);
    return head;
  }

  _navigation() {
    const nav = kretaNode("nav");
    for (const view of KRETA_VIEWS) {
      const button = kretaNode("button", view === this._config.view ? "active" : "", this._text(view));
      button.type = "button";
      button.addEventListener("click", () => {
        this._config = {...this._config, view};
        this._loadedFor = "";
        this._load();
      });
      nav.append(button);
    }
    return nav;
  }

  _content() {
    const view = this._config.view;
    if (view === "overview") return this._overview();
    if (view === "today" || view === "tomorrow") return this._agenda(this._data.lessons, this._text(view));
    if (view === "week") return this._week();
    if (view === "grades") return this._grades();
    return this._generic(view, this._data.items || []);
  }

  _overview() {
    const content = kretaNode("div", "section");
    const current = this._data.current_lesson;
    if (current) content.append(this._hero(current));
    if (this._config.show_next_lesson && this._data.next_lesson) content.append(this._next(this._data.next_lesson));
    content.append(this._agenda(this._data.today.lessons, this._text("today")));
    content.append(this._agenda(this._data.tomorrow.lessons, this._text("tomorrow")));
    const stats = kretaNode("div", "stats");
    for (const [key, value] of Object.entries(this._data.counts || {})) {
      const stat = kretaNode("div", "stat");
      stat.append(kretaNode("strong", "", value), kretaNode("span", "muted", this._text(key)));
      stats.append(stat);
    }
    content.append(stats);
    return content;
  }

  _hero(lesson) {
    const hero = kretaNode("section", "hero");
    hero.append(kretaNode("div", "muted", this._text("current")), kretaNode("h2", "", lesson.subject_name || lesson.summary));
    const details = kretaNode("div", "heroRow");
    if (this._config.show_time) details.append(kretaNode("span", "", `${kretaTime(lesson.start, this._language, this._config.use_24_hour)} – ${kretaTime(lesson.end, this._language, this._config.use_24_hour)}`));
    if (this._config.show_room && lesson.location) details.append(kretaNode("span", "", lesson.location));
    if (this._config.show_teacher && lesson.teacher_name) details.append(kretaNode("span", "", lesson.teacher_name));
    hero.append(details);
    if (this._config.show_progress) {
      const start = new Date(lesson.start).getTime();
      const end = new Date(lesson.end).getTime();
      const progress = Math.max(0, Math.min(100, ((Date.now() - start) / Math.max(1, end - start)) * 100));
      const track = kretaNode("div", "progress");
      const bar = kretaNode("div", "bar");
      bar.style.width = `${progress}%`;
      track.append(bar);
      hero.append(track, kretaNode("div", "muted", `${Math.max(0, Math.ceil((end - Date.now()) / 60000))} ${this._text("remaining")}`));
    }
    return hero;
  }

  _next(lesson) {
    const section = kretaNode("section", "section");
    section.append(kretaNode("h3", "", this._text("next")), this._lesson(lesson));
    return section;
  }

  _agenda(lessons, title) {
    const section = kretaNode("section", "section");
    section.append(kretaNode("h3", "", title));
    const filtered = (lessons || []).filter((item) => this._config.show_cancelled || !item.is_cancelled).filter((item) => item.lesson_index === null || (item.lesson_index >= this._config.first_lesson && item.lesson_index <= this._config.last_lesson));
    if (!filtered.length) section.append(kretaNode("div", "empty", this._text("noSchool")));
    else for (const lesson of filtered) section.append(this._lesson(lesson));
    return section;
  }

  _lesson(lesson) {
    const row = kretaNode("div", `lesson${lesson.is_cancelled ? " cancelled" : ""}`);
    row.tabIndex = 0;
    const time = this._config.show_time ? kretaTime(lesson.start, this._language, this._config.use_24_hour) : (this._config.show_lesson_number ? lesson.lesson_index : "");
    const body = kretaNode("div");
    body.append(kretaNode("div", "subject", lesson.subject_name || lesson.summary || "–"));
    const meta = [];
    if (this._config.show_room && lesson.location) meta.push(lesson.location);
    if (this._config.show_teacher && lesson.teacher_name) meta.push(lesson.teacher_name);
    if (meta.length) body.append(kretaNode("div", "meta", meta.join(" · ")));
    const badges = kretaNode("div", "badges");
    if (lesson.exam) badges.append(kretaNode("span", "badge", this._text("tests")));
    if (this._config.show_substitutions && lesson.is_substitution) badges.append(kretaNode("span", "badge", "↔"));
    if (lesson.is_cancelled) badges.append(kretaNode("span", "badge", "×"));
    row.append(kretaNode("div", "meta", time), body, badges);
    return row;
  }

  _week() {
    const week = kretaNode("div", "week");
    const entries = Object.entries(this._data.days || {}).slice(0, this._config.days_to_show);
    for (const [day, lessons] of entries) {
      const column = kretaNode("section", "day");
      column.append(kretaNode("h3", "", new Date(`${day}T12:00:00`).toLocaleDateString(this._language, {weekday: "long", month: "short", day: "numeric"})));
      const agenda = this._agenda(lessons, "");
      for (const child of [...agenda.children].slice(1)) column.append(child);
      week.append(column);
    }
    return week;
  }

  _grades() {
    const section = kretaNode("section", "section");
    if (this._config.show_grade_statistics) {
      const stats = kretaNode("div", "stats");
      const values = {total: this._data.total, average: this._data.average ?? "–", ...this._data.distribution};
      for (const [key, value] of Object.entries(values)) {
        const item = kretaNode("div", "stat");
        item.append(kretaNode("strong", "", value), kretaNode("span", "muted", key));
        stats.append(item);
      }
      section.append(stats);
    }
    for (const grade of this._data.items || []) section.append(this._dataRow(grade.grade_date, grade.subject_name, grade.value || grade.numeric_value, grade.grade_type));
    if (!(this._data.items || []).length) section.append(kretaNode("div", "empty", this._text("empty")));
    return section;
  }

  _generic(view, items) {
    const section = kretaNode("section", "section");
    section.append(kretaNode("h3", "", this._text(view)));
    for (const item of items) {
      const dateValue = item.test_date || item.due_date || item.absence_date || item.event_date || item.start || item.received_at;
      const main = item.subject_name || item.description || item.subject || item.change_type || item.day_type || "–";
      const value = item.mode || item.status || item.absence_type || item.new_value || "";
      section.append(this._dataRow(dateValue, main, value, item.theme || item.description));
    }
    if (!items.length) section.append(kretaNode("div", "empty", this._text("empty")));
    return section;
  }

  _dataRow(dateValue, main, value, detail) {
    const row = kretaNode("div", "row");
    const shownDate = dateValue ? new Date(dateValue.length === 10 ? `${dateValue}T12:00:00` : dateValue).toLocaleDateString(this._language, {month: "short", day: "numeric"}) : "";
    const body = kretaNode("div");
    body.append(kretaNode("div", "subject", main));
    if (detail) body.append(kretaNode("div", "meta", detail));
    row.append(kretaNode("div", "meta", shownDate), body, kretaNode("div", "badge", value));
    return row;
  }

  _text(key) {
    return KRETA_TEXT[this._language || "en"][key] || key.replaceAll("_", " ");
  }
}

class KretaDashboardCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
  }

  set hass(value) {
    this._hass = value;
    this._render();
  }

  setConfig(config) {
    this._config = {...KRETA_DEFAULTS, ...config};
    this._render();
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const style = kretaNode("style");
    style.textContent = `:host{display:grid;gap:14px;padding:12px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}label{display:grid;gap:5px;color:var(--primary-text-color)}input,select{min-height:42px;padding:0 10px;border:1px solid var(--divider-color);border-radius:8px;background:var(--card-background-color);color:var(--primary-text-color)}.checks{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:8px}.check{display:flex;align-items:center;gap:8px}.check input{min-height:20px;width:20px}`;
    const root = kretaNode("div");
    const grid = kretaNode("div", "grid");
    const fields = [
      ["entry_id", "Account / config entry", "text"], ["title", "Title", "text"], ["accent_color", "Accent color", "color"], ["card_height", "Card height", "text"],
      ["days_to_show", "Days to show", "number"], ["recent_grades", "Recent grades", "number"], ["upcoming_tests", "Upcoming tests", "number"], ["homework_entries", "Homework entries", "number"], ["first_lesson", "First lesson", "number"], ["last_lesson", "Last lesson", "number"]
    ];
    const view = this._select("view", "View", KRETA_VIEWS);
    const week = this._select("week_layout", "Week layout", ["columns", "stacked"]);
    const mobile = this._select("mobile_layout", "Mobile layout", ["scroll", "stacked"]);
    grid.append(view, week, mobile);
    for (const [key, label, type] of fields) grid.append(this._input(key, label, type));
    const checks = kretaNode("div", "checks");
    for (const key of KRETA_BOOLEAN_OPTIONS) {
      const label = kretaNode("label", "check");
      const input = kretaNode("input");
      input.type = "checkbox";
      input.checked = Boolean(this._config[key]);
      input.addEventListener("change", () => this._change(key, input.checked));
      label.append(input, document.createTextNode(key.replaceAll("_", " ")));
      checks.append(label);
    }
    root.append(grid, checks);
    this.shadowRoot.replaceChildren(style, root);
  }

  _input(key, title, type) {
    const label = kretaNode("label", "", title);
    const input = kretaNode("input");
    input.type = type;
    input.value = this._config[key] ?? "";
    input.addEventListener("change", () => this._change(key, type === "number" ? Number(input.value) : input.value));
    label.append(input);
    return label;
  }

  _select(key, title, options) {
    const label = kretaNode("label", "", title);
    const select = kretaNode("select");
    for (const value of options) {
      const option = kretaNode("option", "", value);
      option.value = value;
      option.selected = value === this._config[key];
      select.append(option);
    }
    select.addEventListener("change", () => this._change(key, select.value));
    label.append(select);
    return label;
  }

  _change(key, value) {
    this._config = {...this._config, [key]: value};
    this.dispatchEvent(new CustomEvent("config-changed", {detail: {config: this._config}, bubbles: true, composed: true}));
  }
}

if (!customElements.get("kreta-dashboard-card")) customElements.define("kreta-dashboard-card", KretaDashboardCard);
if (!customElements.get("kreta-dashboard-card-editor")) customElements.define("kreta-dashboard-card-editor", KretaDashboardCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "kreta-dashboard-card")) window.customCards.push({type: "kreta-dashboard-card", name: "KRÉTA Dashboard", description: "Responsive KRÉTA timetable and school dashboard", preview: true});
