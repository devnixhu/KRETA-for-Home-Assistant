const KRETA_VIEWS = ["overview", "today", "tomorrow", "week", "grades", "tests", "homework", "changes", "absences", "messages", "school_year"];
const KRETA_BOOLEAN_OPTIONS = ["show_school_name", "show_teacher", "show_room", "show_lesson_number", "show_time", "show_progress", "show_next_lesson", "show_tests", "show_homework", "show_substitutions", "show_cancelled", "show_grade_statistics", "show_absences", "show_messages", "compact", "dense", "hide_empty_sections", "use_24_hour", "use_theme_color"];
const KRETA_DEFAULTS = {view: "overview", show_school_name: true, show_teacher: true, show_room: true, show_lesson_number: true, show_time: true, show_progress: true, show_next_lesson: true, show_tests: true, show_homework: true, show_substitutions: true, show_cancelled: true, show_grade_statistics: true, show_absences: true, show_messages: true, compact: false, dense: false, days_to_show: 5, recent_grades: 10, upcoming_tests: 10, homework_entries: 10, first_lesson: 0, last_lesson: 10, hide_empty_sections: true, use_24_hour: true, use_theme_color: true, card_height: "auto", week_layout: "columns", mobile_layout: "scroll"};
const KRETA_TEXT = {
  hu: {overview: "Áttekintés", today: "Ma", tomorrow: "Holnap", week: "Hét", grades: "Jegyek", tests: "Dolgozatok", homework: "Házi feladat", changes: "Változások", absences: "Hiányzások", messages: "Üzenetek", school_year: "Tanév", current: "Jelenlegi óra", next: "Következő", noSchool: "Nincs tanítás", empty: "Nincs megjeleníthető adat", loading: "KRÉTA-adatok betöltése…", error: "A KRÉTA-adatok átmenetileg nem érhetők el", partial: "Néhány KRÉTA-adat átmenetileg nem érhető el", remaining: "perc van hátra", total: "Összesen", lastUpdate: "Utolsó frissítés", search: "Keresés", subject: "Tantárgy", all: "Összes", from: "Ettől", to: "Eddig", oldest: "Legrégebbi elöl", newest: "Legújabb elöl", loadMore: "További jegyek", unweighted: "Súlyozatlan átlag", weighted: "Súlyozott átlag", daysRemaining: "nap múlva", overdue: "Lejárt", unread: "olvasatlan", justified: "Igazolt", unjustified: "Igazolatlan", pending: "Függőben", lateMinutes: "Késési percek", late_arrivals: "Késések", this_month: "Ebben a hónapban", thisWeek: "Ezen a héten", later: "Később", nextBreak: "Következő tanévi esemény"},
  en: {overview: "Overview", today: "Today", tomorrow: "Tomorrow", week: "Week", grades: "Grades", tests: "Tests", homework: "Homework", changes: "Changes", absences: "Absences", messages: "Messages", school_year: "School year", current: "Current lesson", next: "Next", noSchool: "No school", empty: "No data to display", loading: "Loading KRÉTA data…", error: "KRÉTA data is temporarily unavailable", partial: "Some KRÉTA data is temporarily unavailable", remaining: "minutes remaining", total: "Total", lastUpdate: "Last update", search: "Search", subject: "Subject", all: "All", from: "From", to: "To", oldest: "Oldest first", newest: "Newest first", loadMore: "More grades", unweighted: "Unweighted average", weighted: "Weighted average", daysRemaining: "days remaining", overdue: "Overdue", unread: "unread", justified: "Justified", unjustified: "Unjustified", pending: "Pending", lateMinutes: "Late minutes", late_arrivals: "Late arrivals", this_month: "This month", thisWeek: "This week", later: "Later", nextBreak: "Next school-year event"}
};
const KRETA_EDITOR_HU = {entry_id: "KRÉTA-fiók", view: "Nézet", title: "Cím", show_school_name: "Iskola neve", show_teacher: "Tanár", show_room: "Terem", show_lesson_number: "Óraszám", show_time: "Időpont", show_progress: "Órahaladás", show_next_lesson: "Következő óra", show_tests: "Dolgozatok", show_homework: "Házi feladat", show_substitutions: "Helyettesítések", show_cancelled: "Elmaradt órák", show_grade_statistics: "Jegystatisztika", show_absences: "Hiányzások", show_messages: "Üzenetek", compact: "Kompakt", dense: "Sűrű", days_to_show: "Napok száma", recent_grades: "Legutóbbi jegyek száma", upcoming_tests: "Közelgő dolgozatok száma", homework_entries: "Házi feladatok száma", first_lesson: "Első óraszám", last_lesson: "Utolsó óraszám", hide_empty_sections: "Üres részek elrejtése", use_24_hour: "24 órás idő", accent_color: "Kiemelőszín", use_theme_color: "HA-téma színe", card_height: "Kártyamagasság", week_layout: "Heti elrendezés", mobile_layout: "Mobil elrendezés"};
const KRETA_VIEW_ICONS = {overview: "⌂", today: "●", tomorrow: "→", week: "▦", grades: "★", tests: "✎", homework: "✓", changes: "↻", absences: "!", messages: "✉", school_year: "◇"};

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

function kretaLocalDate(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

class KretaDashboardCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._request = 0;
    this._timer = null;
    this._reloadTimer = null;
  }

  connectedCallback() {
    if (!this._timer) this._timer = window.setInterval(() => {if (this._config?.view === "overview") this._render();}, 30000);
    if (!this._reloadTimer) this._reloadTimer = window.setInterval(() => {if (!this.shadowRoot.activeElement?.matches("input,select")) this._load();}, 120000);
  }

  disconnectedCallback() {
    window.clearInterval(this._timer);
    window.clearInterval(this._reloadTimer);
    this._timer = null;
    this._reloadTimer = null;
  }

  static getConfigElement() {
    return document.createElement("kreta-dashboard-card-editor");
  }

  static getStubConfig() {
    return {type: "custom:kreta-dashboard-card", ...KRETA_DEFAULTS};
  }

  setConfig(config) {
    this._config = {...KRETA_DEFAULTS, ...config};
    this._gradeFilters = {subject: "", search: "", date_from: "", date_to: "", oldest_first: false};
    this._data = null;
    this._loadedFor = "";
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
    if (!this._config.entry_id) {
      try {
        const result = await this._hass.callWS({type: "kreta/get_entries"});
        if (request !== this._request) return;
        this._entries = result.entries;
        if (result.entries.length === 1) {
          this._config = {...this._config, entry_id: result.entries[0].entry_id};
        } else {
          this._loading = false;
          this._render();
          return;
        }
      } catch (error) {
        if (request !== this._request) return;
        this._loading = false;
        this._error = true;
        this._render();
        return;
      }
    }
    const view = this._config.view;
    let command = "overview";
    const payload = {entry_id: this._config.entry_id};
    const now = new Date();
    if (view === "today" || view === "tomorrow") {
      command = "day";
      if (view === "tomorrow") now.setDate(now.getDate() + 1);
      payload.date = kretaLocalDate(now);
    } else if (view === "week") {
      command = "week";
      payload.date = kretaLocalDate(now);
    } else if (["grades", "tests", "homework", "changes", "absences", "messages", "school_year"].includes(view)) {
      command = view;
      if (["grades", "tests", "homework", "absences", "messages"].includes(view)) payload.limit = this._limitFor(view);
      if (view === "grades") {
        for (const [key, value] of Object.entries(this._gradeFilters)) if (value) payload[key] = value;
      }
    }
    try {
      const data = await this._hass.callWS({type: `kreta/get_${command}`, ...payload});
      if (request !== this._request) return;
      this._data = data;
      this._loadedFor = `${view}:${this._config.entry_id}:${kretaLocalDate(new Date())}`;
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
    if (view === "grades") return Math.max(1, Math.min(200, Number(this._config.recent_grades) || 20));
    if (view === "tests") return Math.max(1, Math.min(200, Number(this._config.upcoming_tests) || 20));
    if (view === "homework") return Math.max(1, Math.min(200, Number(this._config.homework_entries) || 20));
    return 50;
  }

  _style() {
    const style = kretaNode("style");
    style.textContent = `
      :host{display:block}.card{height:var(--kreta-height,auto);overflow:auto;color:var(--primary-text-color);background:var(--ha-card-background,var(--card-background-color));border-radius:var(--ha-card-border-radius,12px);box-shadow:var(--ha-card-box-shadow);font-family:var(--paper-font-body1_-_font-family,inherit)}
      .wrap{padding:18px;display:grid;gap:16px}.dense .wrap{padding:12px;gap:10px}.head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding-bottom:2px}.title{font-size:22px;font-weight:650}.muted{color:var(--secondary-text-color);font-size:13px}.status{width:9px;height:9px;border-radius:50%;background:var(--success-color,#43a047);display:inline-block;margin-right:6px}.status.partial{background:var(--warning-color,#ffa000)}
      .appShell{display:grid;grid-template-columns:174px minmax(0,1fr);gap:18px;align-items:start}.clientContent{min-width:0;display:block}nav{position:sticky;top:8px;display:grid;gap:5px;align-content:start;padding:7px;border-radius:14px;background:var(--secondary-background-color)}nav button{display:grid;grid-template-columns:28px 1fr;align-items:center;text-align:left;gap:7px;min-height:44px;border:0;border-radius:10px;padding:0 11px;background:transparent;color:var(--primary-text-color);cursor:pointer;white-space:nowrap}.navIcon{display:grid;place-items:center;width:25px;height:25px;border-radius:8px;font-size:15px;background:color-mix(in srgb,var(--primary-text-color) 8%,transparent)}nav button.active{background:var(--kreta-accent,var(--primary-color));color:var(--text-primary-color,#fff)}nav button.active .navIcon{background:color-mix(in srgb,#fff 18%,transparent)}button:focus-visible,.lesson:focus-visible{outline:2px solid var(--kreta-accent,var(--primary-color));outline-offset:2px}
      .hero{padding:18px;border-radius:14px;background:color-mix(in srgb,var(--kreta-accent,var(--primary-color)) 12%,var(--card-background-color));display:grid;gap:7px}.hero h2{margin:0;font-size:25px}.heroRow{display:flex;gap:14px;flex-wrap:wrap}.progress{height:7px;background:var(--divider-color);border-radius:8px;overflow:hidden}.bar{height:100%;background:var(--kreta-accent,var(--primary-color));transition:width .25s ease}
      .section{display:grid;gap:9px}.section h3{margin:0;font-size:16px}.lesson,.row{display:grid;grid-template-columns:64px minmax(100px,1fr) auto;gap:12px;align-items:center;padding:11px;border:1px solid var(--divider-color);border-radius:11px;min-height:44px}.lesson.current{border-color:var(--kreta-accent,var(--primary-color));background:color-mix(in srgb,var(--kreta-accent,var(--primary-color)) 8%,transparent)}.lesson.cancelled{opacity:.65;text-decoration:line-through}.subject{font-weight:600}.meta{font-size:13px;color:var(--secondary-text-color)}.badges{display:flex;gap:5px;flex-wrap:wrap;justify-content:flex-end}.badge{border-radius:10px;padding:2px 7px;font-size:11px;background:var(--secondary-background-color)}
      .week{display:grid;grid-template-columns:repeat(5,minmax(190px,1fr));gap:10px;overflow:auto}.stacked .week{grid-template-columns:1fr}.day{display:grid;align-content:start;gap:8px;min-width:190px;padding:7px;border-radius:12px}.day.today{background:color-mix(in srgb,var(--kreta-accent,var(--primary-color)) 7%,transparent)}.day h3{position:sticky;top:0;background:var(--card-background-color);padding:6px 0;z-index:1}.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:9px}.stat{padding:12px;border-radius:10px;background:var(--secondary-background-color)}.stat strong{display:block;font-size:20px}.group{display:grid;gap:8px;margin-top:5px}.groupTitle{font-size:13px;font-weight:650;color:var(--secondary-text-color);text-transform:uppercase;letter-spacing:.04em}.empty,.error,.loading{padding:34px;text-align:center;color:var(--secondary-text-color)}
      .filters{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px}.filters label{display:grid;gap:4px;color:var(--secondary-text-color);font-size:13px}.filters input,.filters select{min-height:44px;padding:0 10px;color:var(--primary-text-color);background:var(--card-background-color);border:1px solid var(--divider-color);border-radius:8px}
      @media(max-width:700px){.wrap{padding:14px}.title{font-size:19px}.appShell{display:block}.clientContent{padding-top:13px}nav{position:sticky;top:0;z-index:4;display:flex;overflow:auto;gap:5px;padding:6px;background:var(--card-background-color);box-shadow:0 5px 12px color-mix(in srgb,#000 10%,transparent)}nav button{display:grid;grid-template-columns:1fr;justify-items:center;gap:2px;min-width:76px;padding:5px 8px;font-size:11px}.navIcon{font-size:14px}.week{grid-template-columns:repeat(5,82vw)}.mobile-stacked .week,.stacked .week{grid-template-columns:1fr}.lesson,.row{grid-template-columns:54px 1fr}.badges{grid-column:2;justify-content:flex-start}.hero{padding:15px}}
    `;
    return style;
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const card = kretaNode("ha-card", `card${this._config.dense || this._config.compact ? " dense" : ""}${this._config.week_layout === "stacked" ? " stacked" : ""}${this._config.mobile_layout === "stacked" ? " mobile-stacked" : ""}`);
    card.style.setProperty("--kreta-height", this._config.card_height || "auto");
    if (!this._config.use_theme_color && this._config.accent_color) card.style.setProperty("--kreta-accent", this._config.accent_color);
    const wrap = kretaNode("div", "wrap");
    const shell = kretaNode("div", "appShell");
    const content = kretaNode("main", "clientContent");
    if (this._loading && !this._data) content.append(kretaNode("div", "loading", this._text("loading")));
    else if (this._error) content.append(kretaNode("div", "error", this._text("error")));
    else if (!this._config.entry_id) content.append(kretaNode("div", "empty", this._language === "hu" ? "Válassz KRÉTA-fiókot a kártyaszerkesztőben" : "Select a KRÉTA account in the card editor"));
    else if (this._data) content.append(this._content());
    shell.append(this._navigation(), content);
    wrap.append(this._header(), shell);
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
    nav.setAttribute("aria-label", this._language === "hu" ? "KRÉTA kliens nézetei" : "KRÉTA client views");
    for (const view of KRETA_VIEWS) {
      if (view === "tests" && !this._config.show_tests) continue;
      if (view === "homework" && !this._config.show_homework) continue;
      if (view === "absences" && !this._config.show_absences) continue;
      if (view === "messages" && !this._config.show_messages) continue;
      const button = kretaNode("button", view === this._config.view ? "active" : "");
      button.type = "button";
      button.title = this._text(view);
      if (view === this._config.view) button.setAttribute("aria-current", "page");
      button.append(kretaNode("span", "navIcon", KRETA_VIEW_ICONS[view]), kretaNode("span", "navLabel", this._text(view)));
      button.addEventListener("click", () => {
        this._config = {...this._config, view};
        this._loadedFor = "";
        this._data = null;
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
    if (view === "tests") return this._datedItems("tests", "test_date", "mode", "theme");
    if (view === "homework") return this._homework();
    if (view === "changes") return this._changes();
    if (view === "absences") return this._absences();
    if (view === "messages") return this._messages();
    if (view === "school_year") return this._schoolYear();
    return this._generic(view, this._data.items || []);
  }

  _overview() {
    const content = kretaNode("div", "section");
    const current = this._data.current_lesson;
    if (current) content.append(this._hero(current));
    if (this._config.show_next_lesson && this._data.next_lesson) content.append(this._next(this._data.next_lesson));
    if (!this._config.hide_empty_sections || this._data.today.lessons.length) content.append(this._agenda(this._data.today.lessons, this._text("today")));
    if (!this._config.hide_empty_sections || this._data.tomorrow.lessons.length) content.append(this._agenda(this._data.tomorrow.lessons, this._text("tomorrow")));
    if (this._data.recent_grades?.length) content.append(this._overviewRows("grades", this._data.recent_grades, "grade_date", "value"));
    if (this._config.show_tests && this._data.upcoming_tests?.length) content.append(this._overviewRows("tests", this._data.upcoming_tests, "test_date", "mode"));
    if (this._config.show_homework && this._data.upcoming_homework?.length) content.append(this._overviewRows("homework", this._data.upcoming_homework, "due_date", "description"));
    if (this._data.recent_changes?.length) content.append(this._overviewRows("changes", this._data.recent_changes, "start", "change_type"));
    if (this._data.next_school_year_event) content.append(this._overviewRows("school_year", [this._data.next_school_year_event], "event_date", "description"));
    const stats = kretaNode("div", "stats");
    for (const [key, value] of Object.entries(this._data.counts || {})) {
      if (key === "tests" && !this._config.show_tests) continue;
      if (key === "homework" && !this._config.show_homework) continue;
      if (key === "absences" && !this._config.show_absences) continue;
      if (key === "messages" && !this._config.show_messages) continue;
      const stat = kretaNode("div", "stat");
      stat.append(kretaNode("strong", "", value), kretaNode("span", "muted", this._text(key)));
      stats.append(stat);
    }
    content.append(stats);
    return content;
  }

  _overviewRows(view, items, dateField, valueField) {
    const section = kretaNode("section", "section");
    section.append(kretaNode("h3", "", this._text(view)));
    for (const item of items) section.append(this._dataRow(item[dateField], item.subject_name || item.description || item.change_type || item.day_type || "–", item[valueField] || "", item.theme || item.topic));
    return section;
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
    const now = Date.now();
    const isCurrent = now >= new Date(lesson.start).getTime() && now < new Date(lesson.end).getTime();
    const row = kretaNode("div", `lesson${lesson.is_cancelled ? " cancelled" : ""}${isCurrent ? " current" : ""}`);
    row.tabIndex = 0;
    const time = this._config.show_time ? kretaTime(lesson.start, this._language, this._config.use_24_hour) : (this._config.show_lesson_number ? lesson.lesson_index : "");
    const body = kretaNode("div");
    body.append(kretaNode("div", "subject", lesson.subject_name || lesson.summary || "–"));
    const meta = [];
    if (this._config.show_room && lesson.location) meta.push(lesson.location);
    if (this._config.show_teacher && lesson.teacher_name) meta.push(lesson.teacher_name);
    if (meta.length) body.append(kretaNode("div", "meta", meta.join(" · ")));
    const badges = kretaNode("div", "badges");
    if (this._config.show_lesson_number && lesson.lesson_index !== null) badges.append(kretaNode("span", "badge", String(lesson.lesson_index)));
    if (this._config.show_tests && lesson.exam) badges.append(kretaNode("span", "badge", this._text("tests")));
    if (this._config.show_substitutions && lesson.is_substitution) badges.append(kretaNode("span", "badge", "↔"));
    if (lesson.is_cancelled) badges.append(kretaNode("span", "badge", "×"));
    row.append(kretaNode("div", "meta", time), body, badges);
    return row;
  }

  _week() {
    const week = kretaNode("div", "week");
    const entries = Object.entries(this._data.days || {}).slice(0, this._config.days_to_show);
    for (const [day, lessons] of entries) {
      const column = kretaNode("section", `day${day === kretaLocalDate(new Date()) ? " today" : ""}`);
      column.append(kretaNode("h3", "", new Date(`${day}T12:00:00`).toLocaleDateString(this._language, {weekday: "long", month: "short", day: "numeric"})));
      const agenda = this._agenda(lessons, "");
      for (const child of [...agenda.children].slice(1)) column.append(child);
      week.append(column);
    }
    return week;
  }

  _grades() {
    const section = kretaNode("section", "section");
    section.append(this._gradeFilterControls());
    if (this._config.show_grade_statistics) {
      const stats = kretaNode("div", "stats");
      const values = {total: this._data.total, average: this._data.average ?? "–", ...this._data.distribution};
      for (const [key, value] of Object.entries(values)) {
        const item = kretaNode("div", "stat");
        item.append(kretaNode("strong", "", value), kretaNode("span", "muted", key));
        stats.append(item);
      }
      section.append(stats);
      section.append(kretaNode("div", "muted", this._data.weighted ? this._text("weighted") : this._text("unweighted")));
    }
    for (const grade of this._data.items || []) section.append(this._dataRow(grade.grade_date, grade.subject_name, grade.value || grade.numeric_value, grade.grade_type));
    if (!(this._data.items || []).length) section.append(kretaNode("div", "empty", this._text("empty")));
    if (this._data.has_more) {
      const more = kretaNode("button", "", this._text("loadMore"));
      more.type = "button";
      more.addEventListener("click", () => this._loadMoreGrades());
      section.append(more);
    }
    return section;
  }

  _datedItems(view, dateField, valueField, detailField) {
    const section = kretaNode("section", "section");
    section.append(kretaNode("h3", "", this._text(view)));
    const items = [...(this._data.items || [])].sort((left, right) => String(left[dateField]).localeCompare(String(right[dateField])));
    for (const item of items) {
      const days = this._daysFromToday(item[dateField]);
      const detail = [item[detailField], item.teacher_name, days >= 0 ? `${days} ${this._text("daysRemaining")}` : this._text("overdue")].filter(Boolean).join(" · ");
      section.append(this._dataRow(item[dateField], item.subject_name || "–", item[valueField] || "", detail));
    }
    if (!items.length) section.append(kretaNode("div", "empty", this._text("empty")));
    return section;
  }

  _homework() {
    const section = kretaNode("section", "section");
    section.append(kretaNode("h3", "", this._text("homework")));
    const groups = new Map([[this._text("overdue"), []], [this._text("today"), []], [this._text("tomorrow"), []], [this._text("thisWeek"), []], [this._text("later"), []]]);
    const today = new Date();
    const weekEnd = new Date(today);
    weekEnd.setDate(today.getDate() + (7 - ((today.getDay() + 6) % 7)));
    weekEnd.setHours(23, 59, 59, 999);
    for (const item of [...(this._data.items || [])].sort((left, right) => left.due_date.localeCompare(right.due_date))) {
      const days = this._daysFromToday(item.due_date);
      const target = days < 0 ? this._text("overdue") : days === 0 ? this._text("today") : days === 1 ? this._text("tomorrow") : new Date(`${item.due_date}T12:00:00`) <= weekEnd ? this._text("thisWeek") : this._text("later");
      groups.get(target).push(item);
    }
    for (const [title, items] of groups) {
      if (!items.length) continue;
      const group = kretaNode("div", "group");
      group.append(kretaNode("div", "groupTitle", title));
      for (const item of items) group.append(this._dataRow(item.due_date, item.subject_name || "–", this._daysFromToday(item.due_date) < 0 ? this._text("overdue") : "", item.description));
      section.append(group);
    }
    if (!(this._data.items || []).length) section.append(kretaNode("div", "empty", this._text("empty")));
    return section;
  }

  _changes() {
    const section = kretaNode("section", "section");
    section.append(kretaNode("h3", "", this._text("changes")));
    for (const item of this._data.items || []) {
      const transition = [item.old_value, item.new_value].filter((value) => value !== null && value !== undefined && value !== "").join(" → ");
      section.append(this._dataRow(item.start, item.subject_name || "–", item.lesson_index ?? "", `${this._text(item.change_type)}${transition ? ` · ${transition}` : ""}`));
    }
    if (!(this._data.items || []).length) section.append(kretaNode("div", "empty", this._text("empty")));
    return section;
  }

  _absences() {
    const section = kretaNode("section", "section");
    section.append(kretaNode("h3", "", this._text("absences")));
    const items = this._data.items || [];
    const stats = this._data.summary || {total: this._data.total || 0};
    const summary = kretaNode("div", "stats");
    for (const [key, value] of Object.entries(stats)) {
      const stat = kretaNode("div", "stat");
      stat.append(kretaNode("strong", "", value), kretaNode("span", "muted", this._text(key === "late_minutes" ? "lateMinutes" : key)));
      summary.append(stat);
    }
    section.append(summary);
    for (const item of items) section.append(this._dataRow(item.absence_date, item.subject_name || item.absence_type || "–", item.minutes ? `${item.minutes} min` : item.absence_type, item.status));
    if (!items.length) section.append(kretaNode("div", "empty", this._text("empty")));
    return section;
  }

  _messages() {
    const section = kretaNode("section", "section");
    section.append(kretaNode("h3", "", this._text("messages")));
    for (const item of this._data.items || []) section.append(this._dataRow(item.received_at, item.subject || "–", item.is_read ? "" : this._text("unread"), item.sender));
    if (!(this._data.items || []).length) section.append(kretaNode("div", "empty", this._text("empty")));
    return section;
  }

  _schoolYear() {
    const section = kretaNode("section", "section");
    const items = this._data.items || [];
    if (items.length) {
      const first = items[0];
      const hero = kretaNode("section", "hero");
      hero.append(kretaNode("div", "muted", this._text("nextBreak")), kretaNode("h2", "", first.description || first.day_type || "–"), kretaNode("div", "heroRow", new Date(`${first.event_date}T12:00:00`).toLocaleDateString(this._language, {year: "numeric", month: "long", day: "numeric"})));
      section.append(hero);
    }
    for (const item of items.slice(1)) section.append(this._dataRow(item.event_date, item.description || item.day_type || "–", item.day_type || "", `${this._daysFromToday(item.event_date)} ${this._text("daysRemaining")}`));
    if (!items.length) section.append(kretaNode("div", "empty", this._text("empty")));
    return section;
  }

  _daysFromToday(value) {
    const target = new Date(`${String(value).slice(0, 10)}T12:00:00`);
    const today = new Date();
    today.setHours(12, 0, 0, 0);
    return Math.round((target.getTime() - today.getTime()) / 86400000);
  }

  _gradeFilterControls() {
    const filters = kretaNode("div", "filters");
    const search = this._filterInput("search", "text");
    const from = this._filterInput("date_from", "date", "from");
    const to = this._filterInput("date_to", "date", "to");
    const subjectLabel = kretaNode("label", "", this._text("subject"));
    const subject = kretaNode("select");
    const all = kretaNode("option", "", this._text("all"));
    all.value = "";
    subject.append(all);
    for (const value of this._data.subjects || []) {
      const option = kretaNode("option", "", value);
      option.value = value;
      option.selected = value === this._gradeFilters.subject;
      subject.append(option);
    }
    subject.addEventListener("change", () => this._changeGradeFilter("subject", subject.value));
    subjectLabel.append(subject);
    const sortLabel = kretaNode("label", "", this._text("newest"));
    const sort = kretaNode("select");
    for (const [value, label] of [["newest", this._text("newest")], ["oldest", this._text("oldest")]]) {
      const option = kretaNode("option", "", label);
      option.value = value;
      option.selected = (value === "oldest") === this._gradeFilters.oldest_first;
      sort.append(option);
    }
    sort.addEventListener("change", () => this._changeGradeFilter("oldest_first", sort.value === "oldest"));
    sortLabel.append(sort);
    filters.append(search, subjectLabel, from, to, sortLabel);
    return filters;
  }

  _filterInput(key, type, labelKey) {
    const label = kretaNode("label", "", this._text(labelKey || key));
    const input = kretaNode("input");
    input.type = type;
    input.value = this._gradeFilters[key] || "";
    input.addEventListener("change", () => this._changeGradeFilter(key, input.value));
    label.append(input);
    return label;
  }

  _changeGradeFilter(key, value) {
    this._gradeFilters = {...this._gradeFilters, [key]: value};
    this._data = null;
    this._load();
  }

  async _loadMoreGrades() {
    if (!this._hass || !this._data || this._loadingMore) return;
    this._loadingMore = true;
    const payload = {type: "kreta/get_grades", entry_id: this._config.entry_id, limit: this._limitFor("grades"), offset: this._data.items.length};
    for (const [key, value] of Object.entries(this._gradeFilters)) if (value) payload[key] = value;
    try {
      const result = await this._hass.callWS(payload);
      this._data = {...result, items: [...this._data.items, ...result.items]};
      this._render();
    } catch (error) {
      this._error = true;
      this._render();
    } finally {
      this._loadingMore = false;
    }
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
    this._language = value.language === "hu" ? "hu" : "en";
    if (!this._entries && !this._loadingEntries) this._loadEntries();
    this._render();
  }

  async _loadEntries() {
    if (!this._hass) return;
    this._loadingEntries = true;
    try {
      const result = await this._hass.callWS({type: "kreta/get_entries"});
      this._entries = result.entries;
      if (!this._config?.entry_id && this._entries.length === 1) this._change("entry_id", this._entries[0].entry_id);
      this._render();
    } catch (error) {
      this._entries = [];
      this._render();
    } finally {
      this._loadingEntries = false;
    }
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
      ["title", "Title", "text"], ["accent_color", "Accent color", "color"], ["card_height", "Card height", "text"],
      ["days_to_show", "Days to show", "number"], ["recent_grades", "Recent grades", "number"], ["upcoming_tests", "Upcoming tests", "number"], ["homework_entries", "Homework entries", "number"], ["first_lesson", "First lesson", "number"], ["last_lesson", "Last lesson", "number"]
    ];
    const account = this._select("entry_id", this._label("entry_id", "Account"), (this._entries || []).map((item) => [item.entry_id, item.title]));
    const view = this._select("view", this._label("view"), KRETA_VIEWS);
    const week = this._select("week_layout", this._label("week_layout"), ["columns", "stacked"]);
    const mobile = this._select("mobile_layout", this._label("mobile_layout"), ["scroll", "stacked"]);
    grid.append(account, view, week, mobile);
    for (const [key, label, type] of fields) grid.append(this._input(key, this._label(key, label), type));
    const checks = kretaNode("div", "checks");
    for (const key of KRETA_BOOLEAN_OPTIONS) {
      const label = kretaNode("label", "check");
      const input = kretaNode("input");
      input.type = "checkbox";
      input.checked = Boolean(this._config[key]);
      input.addEventListener("change", () => this._change(key, input.checked));
      label.append(input, document.createTextNode(this._label(key)));
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
    if (key === "entry_id") {
      const empty = kretaNode("option", "", "—");
      empty.value = "";
      select.append(empty);
    }
    for (const item of options) {
      const value = Array.isArray(item) ? item[0] : item;
      const option = kretaNode("option", "", Array.isArray(item) ? item[1] : value);
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

  _label(key, fallback) {
    return this._language === "hu" ? (KRETA_EDITOR_HU[key] || fallback || key) : (fallback || key.replaceAll("_", " "));
  }
}

if (!customElements.get("kreta-dashboard-card")) customElements.define("kreta-dashboard-card", KretaDashboardCard);
if (!customElements.get("kreta-dashboard-card-editor")) customElements.define("kreta-dashboard-card-editor", KretaDashboardCardEditor);
window.customCards = window.customCards || [];
if (!window.customCards.some((card) => card.type === "kreta-dashboard-card")) window.customCards.push({type: "kreta-dashboard-card", name: "KRÉTA kliens", description: "Reszponzív KRÉTA-kliens órarenddel és tanulmányi adatokkal", preview: true});
