/*
 * Home Price Card – spotové ceny elektriny (OKTE) a plán batérie ako časová os.
 *
 *   Súčasť integrácie AI Energy – načíta sa automaticky, entity sa doplnia samé.
 *
 *   type: custom:home-price-card
 *   title: Cena elektriny
 *   price_entity: sensor.ai_energy_ceny          # atribút ceny: [{t: unix s, p: €/MWh}, …] po 15 min
 *   threshold_entity: input_number.ai_fve_prah     # prah predaja – ceny nad ním sú zelené
 *   plan_entity: sensor.ai_fve_plan                # voliteľné – template senzor AI plánu (sloty [[t, soc, akcia]])
 *   soc_entity: sensor.smartshunt_soc_keep         # voliteľné – aktuálne SOC
 *   merge: 30                                      # voliteľné – bloky ≤ 30 min sa zlúčia do susedného (bodka „+ ●“)
 *   thresholds: [15, 88, 185]                      # voliteľné – 2. hodnota = hranica „lacné“ (svetlosivá) vs „bežné“ (sivá)
 *   unit: €/MWh
 */
(function () {
  'use strict';
  const VERSION = '2.6.2';
  // cena: neutrálna škála (nekoliduje s farbami akcií) – lacné svetlé, bežné sivé, nad prahom predaja zelená (ako predaj)
const C = { cheap: '#d1d1d6', norm: '#8e8e93', high: '#30d158', sol: '#ffc53d' };
  const ACT = {
    // zelená = peniaze idú k nám, červená = platíme sieti, oranžová/žltá = slnko, modrá = batéria napája dom
    P: { t: 'Predaj z batérie', c: '#30d158', e: '💰' }, E: { t: 'Predaj len z FVE', c: '#b4e34f', e: '🌤️' }, N: { t: 'Nabíjanie zo siete', c: '#ff453a', e: '🔋' }, F: { t: 'FVE nabíja batériu', c: '#ff9f0a', e: '☀️' },
    O: { t: 'Batéria plná, prebytok do siete', c: '#ffd60a', e: '☀️' }, G: { t: 'Dom zo siete, batéria stojí', c: '#636366', e: '⏸️' }, D: { t: 'Dom z batérie', c: '#64d2ff', e: '🏠' }
  };
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]); }
  const ui = (p) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="${p}"/></svg>`;

  const CSS = `
    ha-card { padding: 12px 16px 14px; overflow: hidden; }
    .hl { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--secondary-text-color); letter-spacing: .02em; }
    .hl svg { width: 16px; height: 16px; }
    .seg { margin-left: auto; display: inline-flex; padding: 2px; border-radius: 9px; background: var(--hc-surface, rgba(127,127,127,.12)); }
    .seg b { font-size: 12px; font-weight: 500; padding: 3px 10px; border-radius: 7px; color: var(--primary-text-color); cursor: pointer; }
    .seg b.on { background: var(--primary-text-color); color: var(--card-background-color, #1c1c1e); }
    .seg b.dis { opacity: .35; pointer-events: none; }
    .num { font-variant-numeric: tabular-nums; }
    .box { border-radius: 16px; background: var(--hc-surface, rgba(127,127,127,.1)); box-shadow: inset 0 0 0 1px var(--hc-surface-line, transparent); }
    .sub { display: flex; font-size: 11px; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .06em; margin: 14px 2px 6px; }
    .sub span { margin-left: auto; text-transform: none; letter-spacing: 0; }
    .pr { margin-top: 12px; padding: 10px 12px 4px; cursor: pointer; }
    .pt { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; font-size: 12px; color: var(--secondary-text-color); margin-bottom: 8px; }
    .pt b { font-size: 18px; font-weight: 600; color: var(--primary-text-color); } .pt i { font-style: normal; } .pt small { font-size: 11px; }
    .ch { position: relative; margin-left: 26px; }
    .ch svg { display: block; width: 100%; overflow: visible; }
    .ch { touch-action: pan-y; cursor: crosshair; }
    .hov { position: absolute; top: 0; height: 100px; width: 0; border-left: 1px dashed var(--primary-text-color); opacity: 0; pointer-events: none; }
    .tip { position: absolute; top: -6px; transform: translate(-50%, -100%); padding: 6px 9px; border-radius: 10px; background: rgba(28,28,32,.92); color: #fff; font-size: 11px; line-height: 1.35; white-space: nowrap; box-shadow: 0 4px 14px rgba(0,0,0,.35); opacity: 0; pointer-events: none; transition: opacity .12s; z-index: 2; }
    .tip b { font-size: 15px; font-weight: 600; } .tip small { color: #aeaeb2; }
    .tip span { display: block; color: #d1d1d6; } .tip span i { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; }
    .tip.on, .hov.on { opacity: 1; }
    .hov.on { opacity: .6; }
    .yl { position: absolute; right: calc(100% + 6px); font-size: 10px; color: var(--secondary-text-color); transform: translateY(-50%); }
    .xa { margin-left: 26px; }
    .it.x, .tg, .col { cursor: pointer; }
    .sub.tg { align-items: center; }
    .chev { display: inline-flex; margin-left: auto; transition: transform .2s; transform: rotate(-90deg); }
    .chev svg { width: 16px; height: 16px; } .chev.o { transform: none; }
    .col .it { min-height: 0 !important; }
    .more { font-size: 12px; color: var(--secondary-text-color); padding: 0 0 2px 72px; }
    .it .bd .chev { width: 14px; height: 14px; margin-left: 4px; vertical-align: -3px; }
    .it .bd .chev svg { width: 14px; height: 14px; }
    .det { grid-column: 3 / 5; margin: -4px 0 10px; padding: 6px 10px; border-radius: 10px; background: var(--hc-surface, rgba(127,127,127,.1)); }
    .dr { display: grid; grid-template-columns: 8px 82px 1fr auto; gap: 8px; align-items: center; font-size: 12px; color: var(--primary-text-color); padding: 3px 0; }
    .dr i { width: 8px; height: 8px; border-radius: 50%; } .dr .dn small { color: var(--secondary-text-color); } .dr .ds { color: var(--secondary-text-color); }
    .dr.past { opacity: .45; }
    .pg { display: block; height: 3px; border-radius: 2px; background: rgba(127,127,127,.2); margin-top: 6px; max-width: 160px; overflow: hidden; }
    .pg i { display: block; height: 100%; border-radius: 2px; }
    .xa { position: relative; height: 14px; font-size: 10px; color: var(--secondary-text-color); }
    .xa span { position: absolute; transform: translateX(-50%); } .xa span:first-child { transform: none; } .xa span:last-child { transform: translateX(-100%); }
    .it { display: grid; grid-template-columns: 42px 22px 1fr auto; column-gap: 8px; }
    .it .tm { font-size: 13px; font-weight: 600; padding-top: 8px; text-align: right; color: var(--primary-text-color); }
    .it .rail { position: relative; grid-row: span 2; } .it .tm { grid-row: span 2; }
    .it .rail:before { content: ''; position: absolute; left: 10px; top: 0; bottom: 0; width: 2px; background: var(--c); opacity: .5; }
    .it .rail i { position: absolute; left: 5px; top: 11px; width: 12px; height: 12px; border-radius: 50%; background: var(--c); }
    .it.cur .rail i { box-shadow: 0 0 0 4px color-mix(in srgb, var(--c) 30%, transparent); }
    .it .bd { padding: 7px 0 12px; font-size: 14px; color: var(--primary-text-color); min-width: 0; }
    .it.cur .bd { font-weight: 600; }
    .it .bd small { display: block; font-size: 12px; color: var(--secondary-text-color); margin-top: 2px; font-weight: 400; }
    .it .rt { padding-top: 7px; text-align: right; font-size: 13px; color: var(--primary-text-color); opacity: .85; white-space: nowrap; }
    .it.past { opacity: .4; }
    .it.end .bd { color: var(--secondary-text-color); }
    .bat { display: block; margin: 6px 0 0 auto; width: 46px; height: 7px; border-radius: 3px; background: rgba(127,127,127,.22); position: relative; overflow: hidden; }
    .bat i { position: absolute; top: 0; bottom: 0; }
    .done { font-size: 12px; color: var(--secondary-text-color); padding: 2px 0 10px 72px; cursor: pointer; }
    .msg { font-size: 13px; color: var(--secondary-text-color); padding: 8px 0; }
  `;

  class HomePriceCard extends HTMLElement {
    static getConfigElement() { return document.createElement('home-price-card-editor'); }
    static getStubConfig(hass) {
      const st = hass ? hass.states : {}, f = (re) => Object.keys(st).find((id) => re.test(id));
      const c = { price_entity: f(/^sensor\.ai_energy_ceny$/) || f(/^sensor\.okte_ceny/) || 'sensor.ai_energy_ceny' };
      [['threshold_entity', /^number\.ai_energy_prah_predaja$|^input_number\.ai_fve_prah/], ['plan_entity', /^sensor\.ai_energy_plan$|^sensor\.ai_fve_plan/]].forEach(([k, re]) => { const x = f(re); if (x) c[k] = x; });
      // SOC: entita, ktorú má AI Energy nastavenú (atribút plánu nemáme) – inak prvá s "soc" a device_class battery
      const soc = Object.keys(st).find((id) => /^sensor\./.test(id) && /soc/.test(id) && st[id].attributes.device_class === 'battery');
      if (soc) c.soc_entity = soc;
      return c;
    }
    setConfig(c) {
      if (!c || !c.price_entity) throw new Error('Zadaj price_entity (senzor s atribútom ceny).');
      this._cfg = Object.assign({ title: 'Cena elektriny', unit: '€/MWh', thresholds: [15, 88, 185], merge: 30 }, c);
      this._built = false; this._day = this._day || 0;
      if (this._open == null) { try { this._open = localStorage.getItem('hpc-open') === '1'; } catch (z) { this._open = false; } }
      if (this._hass) this._render();
    }
    set hass(h) { this._hass = h; if (this._cfg) this._render(); }
    connectedCallback() { if (!this._t) this._t = setInterval(() => { this._sig = ''; this._render(); }, 60000); }
    disconnectedCallback() { clearInterval(this._t); this._t = null; }
    getCardSize() { return 8; }
    getGridOptions() { return { columns: 12, min_columns: 6 }; }

    _st(id) { return id && this._hass.states[id]; }
    _hm(t) { const d = new Date(t); return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0'); }
    _dur(ms) { const m = Math.round(ms / 60000), h = Math.floor(m / 60); return (h ? h + ' h' : '') + (h && m % 60 ? ' ' : '') + (m % 60 ? (m % 60) + ' min' : ''); }
    _prah() { const s = this._st(this._cfg.threshold_entity); const v = s ? parseFloat(s.state) : NaN; return isNaN(v) ? (this._cfg.threshold != null ? +this._cfg.threshold : null) : v; }
    _col(p, prah) { const t = this._cfg.thresholds || []; if (prah != null && p >= prah) return C.high; if (p < (t[1] != null ? t[1] : 88)) return C.cheap; return C.norm; }

    // sloty plánu → bloky; krátke prepnutia (≤ merge min) sa zlúčia do susedného bloku a zapamätajú ako „mix“
    _blocks(sl, socStart) {
      let b = [];
      sl.forEach((s) => { const l = b[b.length - 1]; if (l && l.c === s[2] && l.sl[l.sl.length - 1][0] + 900000 === s[0]) l.sl.push(s); else b.push({ c: s[2], sl: [s], mix: {} }); });
      const lim = Math.floor((+this._cfg.merge || 0) / 15);   // počet 15-min slotov; 0 = nezlučovať
      let ch = true;
      while (ch) {
        ch = false;
        for (let i = 0; lim > 0 && i < b.length && b.length > 1; i++) {
          if (b[i].sl.length > lim) continue;
          const j = i > 0 ? i - 1 : i + 1, t = b[j];
          if (t.sl[0][0] > b[i].sl[0][0]) t.sl = b[i].sl.concat(t.sl); else t.sl = t.sl.concat(b[i].sl);
          t.mix[b[i].c] = 1; Object.assign(t.mix, b[i].mix); b.splice(i, 1); ch = true; break;
        }
        for (let i = 1; !ch && i < b.length; i++) if (b[i].c === b[i - 1].c) { b[i - 1].sl = b[i - 1].sl.concat(b[i].sl); Object.assign(b[i - 1].mix, b[i].mix); b.splice(i, 1); ch = true; }
      }
      return b.map((x) => {
        const k = sl.indexOf(x.sl[0]), s0 = k > 0 ? sl[k - 1][1] : socStart;
        return { c: x.c, t: x.sl[0][0], e: x.sl[x.sl.length - 1][0] + 900000, s0: s0 != null && !isNaN(s0) ? s0 : x.sl[0][1], s1: x.sl[x.sl.length - 1][1], sl: x.sl, mix: Object.keys(x.mix).filter((m) => m !== x.c && ACT[m]) };
      });
    }

    _tip(ch, cx) {
      const d = this._tipD; if (!d || !d.day.length) return;
      const r = ch.getBoundingClientRect(), f = Math.max(0, Math.min(0.9999, (cx - r.left) / r.width));
      const t = d.T0 + Math.floor(f * 96) * 900000, x = d.day.find((p) => p[0] === t); if (!x) return this._tipHide();
      const s = d.sl.find((q) => q[0] === t), a = s && ACT[s[2]], l = ((t - d.T0) / 864000 + 100 / 192);
      const tp = ch.querySelector('.tip'), hv = ch.querySelector('.hov');
      tp.innerHTML = `<b class="num" style="color:${this._col(x[1], d.prah) === C.high ? C.high : 'inherit'}">${Math.round(x[1])}</b> <small>${esc(d.unit)}</small><span class="num">${this._hm(t)}–${this._hm(t + 900000)}</span>${a ? `<span><i style="background:${a.c}"></i>${a.t}</span>` : ''}`;
      tp.style.left = Math.max(14, Math.min(86, l)) + '%'; tp.classList.add('on');
      hv.style.left = l + '%'; hv.classList.add('on');
    }
    _tipHide() { const r = this.shadowRoot; if (!r) return; r.querySelectorAll('.tip.on, .hov.on').forEach((e) => e.classList.remove('on')); }
    _render() {
      if (!this._hass || !this._cfg) return;
      const c = this._cfg, ps = this._st(c.price_entity), pl = this._st(c.plan_entity), se = this._st(c.soc_entity);
      const sig = [ps && ps.last_updated, pl && pl.last_updated, this._prah(), this._day, this._past, this._open, [...(this._exp || [])].join(','), se && se.state, Math.floor(Date.now() / 60000)].join('|');
      if (this._built && sig === this._sig) return; this._sig = sig;
      if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
      if (!this._built) {
        this.shadowRoot.innerHTML = `<style>${CSS}</style><ha-card><div id="c"></div></ha-card>`;
        this._built = true;
        const card = this.shadowRoot.querySelector('ha-card');
        // tooltip nad grafom – myš (hover) aj prst (ťuknutie / ťahanie)
        const tip = (e) => { const ch = e.target.closest && e.target.closest('.ch'); if (!ch) return; this._tip(ch, e.clientX); if (e.pointerType !== 'mouse') { clearTimeout(this._tipT); this._tipT = setTimeout(() => this._tipHide(), 3500); } };
        card.addEventListener('pointermove', tip); card.addEventListener('pointerdown', tip);
        card.addEventListener('pointerleave', () => this._tipHide()); card.addEventListener('pointerout', (e) => { if (e.pointerType === 'mouse' && e.target.closest && e.target.closest('.ch') && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('.ch'))) this._tipHide(); });
        card.addEventListener('click', (e) => {
          const d = e.target.closest('[data-day]'); if (d) { this._day = +d.dataset.day; this._sig = ''; this._render(); return; }
          if (e.target.closest('[data-past]')) { this._past = !this._past; this._sig = ''; this._render(); return; }
          if (e.target.closest('[data-open]')) { this._open = !this._open; try { localStorage.setItem('hpc-open', this._open ? '1' : '0'); } catch (z) { /* */ } this._sig = ''; this._render(); return; }
          const x = e.target.closest('[data-x]'); if (x) { const k = +x.dataset.x, s = this._exp || (this._exp = new Set()); if (s.has(k)) s.delete(k); else s.add(k); this._sig = ''; this._render(); return; }
          const m = e.target.closest('[data-more]'); if (m && m.dataset.more) this.dispatchEvent(new CustomEvent('hass-more-info', { detail: { entityId: m.dataset.more }, bubbles: true, composed: true }));
        });
      }
      const box = this.shadowRoot.getElementById('c');
      if (!ps) { box.innerHTML = `<div class="msg">Entita ${esc(c.price_entity)} neexistuje.</div>`; return; }
      const now = Date.now(), d0 = new Date(); d0.setHours(0, 0, 0, 0);
      const all = (ps.attributes.ceny || ps.attributes.prices || []).map((x) => [(+x.t) * (x.t < 1e12 ? 1000 : 1), +x.p]).filter((x) => !isNaN(x[1])).sort((a, b) => a[0] - b[0]);
      const t1 = d0.getTime() + 86400000, hasTom = all.some((x) => x[0] >= t1 && x[0] < t1 + 86400000);
      if (this._day === 1 && !hasTom) this._day = 0;
      const T0 = d0.getTime() + this._day * 86400000, T1 = T0 + 86400000, isToday = this._day === 0;
      const day = all.filter((x) => x[0] >= T0 && x[0] < T1), prah = this._prah(), unit = c.unit;
      const pmap = {}; day.forEach((x) => { pmap[x[0]] = x[1]; });
      const avg = (a, b) => { const v = day.filter((x) => x[0] >= a && x[0] < b).map((x) => x[1]); return v.length ? v.reduce((p, q) => p + q, 0) / v.length : null; };
      let h = `<div class="hl">${ui('M13 2 4 14h7l-1 8 9-12h-7z')}<span>${esc(c.title)}</span><div class="seg"><b data-day="0" class="${isToday ? 'on' : ''}">Dnes</b><b data-day="1" class="${!isToday ? 'on' : ''}${hasTom ? '' : ' dis'}">Zajtra</b></div></div>`;
      if (!day.length) { box.innerHTML = h + '<div class="msg">Pre tento deň zatiaľ nie sú ceny.</div>'; box.__h = ''; return; }
      // plán → bloky
      const sl = pl ? (pl.attributes.sloty || []).map((x) => [(+x[0]) * 1000, +x[1], x[2]]).filter((x) => ACT[x[2]]) : [];
      const socNow = parseFloat(se && se.state);
      const blocks = this._blocks(sl, isNaN(socNow) ? null : socNow).filter((b) => b.e > T0 && b.t < T1);
      const cb = isToday ? blocks.find((b) => b.t <= now && now < b.e) : null;
      // graf cien + pás plánu
      const X = (t) => (t - T0) / 864000, bw = 100 / 96, H = 100;
      const pmin = Math.min(0, ...day.map((x) => x[1])), pmax = Math.max(100, Math.ceil(Math.max(...day.map((x) => x[1]), prah || 0) / 100) * 100);
      const Y = (v) => H - (v - pmin) / (pmax - pmin) * H, y0 = Y(0);
      let svg = `<svg viewBox="0 0 100 ${H + 12}" preserveAspectRatio="none" style="height:${H + 12}px">`, yl = '';
      for (let v = 100; v <= pmax; v += 100) { svg += `<line x1="0" x2="100" y1="${Y(v).toFixed(2)}" y2="${Y(v).toFixed(2)}" stroke="currentColor" stroke-opacity=".08" vector-effect="non-scaling-stroke"/>`; yl += `<span class="yl" style="top:${Y(v).toFixed(1)}px">${v}</span>`; }
      if (prah != null) svg += `<line x1="0" x2="100" y1="${Y(prah).toFixed(2)}" y2="${Y(prah).toFixed(2)}" stroke="${C.high}" stroke-opacity=".75" stroke-dasharray="3 3" vector-effect="non-scaling-stroke"/>`;
      svg += day.map((x) => { const y = Y(x[1]), top = Math.min(y, y0), hh = Math.max(0.6, Math.abs(y0 - y)); return `<rect x="${(X(x[0]) + bw * .1).toFixed(2)}" y="${top.toFixed(2)}" width="${(bw * .8).toFixed(2)}" height="${hh.toFixed(2)}" fill="${this._col(x[1], prah)}" opacity="${isToday && x[0] + 900000 <= now ? .3 : .85}"/>`; }).join('');
      svg += blocks.map((b) => { const a = Math.max(b.t, T0), z = Math.min(b.e, T1); return `<rect x="${(X(a) + .15).toFixed(2)}" y="${H + 6}" width="${Math.max(.3, X(z) - X(a) - .3).toFixed(2)}" height="6" fill="${ACT[b.c].c}" opacity="${isToday && b.e <= now ? .35 : 1}"/>`; }).join('');
      if (isToday) svg += `<line x1="${X(now).toFixed(2)}" x2="${X(now).toFixed(2)}" y1="0" y2="${H + 12}" stroke="currentColor" stroke-width="1.2" vector-effect="non-scaling-stroke"/>`;
      svg += '</svg>';
      const xa = `<div class="xa">${[0, 6, 12, 18, 24].map((hh) => `<span style="left:${hh / 24 * 100}%">${String(hh).padStart(2, '0')}</span>`).join('')}</div>`;
      const cp = isToday ? day.find((x) => x[0] <= now && now < x[0] + 900000) : null;
      const lo = day.reduce((a, x) => x[1] < a[1] ? x : a), hi = day.reduce((a, x) => x[1] > a[1] ? x : a);
      const info = cp ? `teraz <b style="color:${this._col(cp[1], prah) === C.high ? C.high : 'var(--primary-text-color)'}">${Math.round(cp[1])}</b>` : `Ø <b>${Math.round(avg(T0, T1))}</b>`;
      h += `<div class="box pr"><div class="pt num"><span>${info} <small>${esc(unit)}</small></span><span>min ${Math.round(lo[1])} · max ${Math.round(hi[1])}${prah != null ? ` · <i style="color:${C.high}">prah ${Math.round(prah)}</i>` : ''}</span></div><div class="ch">${svg}${yl}<div class="hov"></div><div class="tip"></div></div>${xa}</div>`;
      this._tipD = { day, T0, H, prah, unit, sl };
      // časová os (rozbaľovacia)
      if (blocks.length) {
        const past = isToday ? blocks.filter((b) => b.e <= now) : [], next = blocks.filter((b) => !past.includes(b));
        const exp = this._exp || (this._exp = new Set()), open = !!this._open;
        const socBefore = (t, dflt) => { const k = sl.findIndex((x) => x[0] >= t); return k > 0 ? sl[k - 1][1] : dflt; };
        const row = (b) => {
          const a = ACT[b.c], bt = Math.max(b.t, T0), be = Math.min(b.e, T1), dur = be - bt, av = avg(bt, be), cur = b === cb, ps0 = b.e <= now && isToday;
          // blok cez polnoc – SOC len za časť v tomto dni
          const kin = b.sl.filter((x) => x[0] >= bt && x[0] < be), s0 = cur && !isNaN(socNow) ? socNow : (bt > b.t ? socBefore(bt, b.s0) : b.s0), s1 = kin.length ? kin[kin.length - 1][1] : b.s1;
          const lo = Math.max(0, Math.min(100, Math.min(s0, s1))), hi = Math.max(0, Math.min(100, Math.max(s0, s1)));
          const isX = b.mix.length > 0 && open, op = isX && exp.has(b.t);
          const mix = b.mix.length ? ` · + ${b.mix.map((m) => `<span style="color:${ACT[m].c}">●</span>`).join(' ')}${isX ? `<span class="chev${op ? ' o' : ''}">${ui('m6 9 6 6 6-6')}</span>` : ''}` : '';
          const sub = cur ? `do ${this._hm(be)} · ešte ${this._dur(be - now)}${mix}` : `${this._dur(dur)}${av != null ? ' · Ø ' + Math.round(av) + ' ' + esc(unit) : ''}${mix}`;
          const pg = cur ? `<span class="pg"><i style="width:${Math.max(0, Math.min(100, (now - bt) / dur * 100)).toFixed(1)}%;background:${a.c}"></i></span>` : '';
          // rozbalenie: pôvodné úseky v rámci bloku
          let det = '';
          if (op) {
            const runs = []; kin.forEach((x) => { const l = runs[runs.length - 1]; if (l && l.c === x[2] && l.e === x[0]) { l.e = x[0] + 900000; l.s1 = x[1]; } else runs.push({ c: x[2], t: x[0], e: x[0] + 900000, s0: socBefore(x[0], x[1]), s1: x[1] }); });
            det = `<div class="det">${runs.map((r) => { const ra = avg(r.t, r.e), pr = isToday && r.e <= now; return `<div class="dr${pr ? ' past' : ''}"><i style="background:${ACT[r.c].c}"></i><span class="num">${this._hm(r.t)}–${this._hm(r.e)}</span><span class="dn">${ACT[r.c].t}${ra != null ? `<small class="num"> · ${Math.round(ra)}</small>` : ''}</span><span class="num ds">${Math.round(r.s0)} → ${Math.round(r.s1)} %</span></div>`; }).join('')}</div>`;
          }
          return `<div class="it${cur ? ' cur' : ''}${ps0 ? ' past' : ''}${isX ? ' x' : ''}" ${isX ? `data-x="${b.t}"` : ''} style="--c:${a.c};min-height:${Math.round(Math.max(46, Math.min(104, dur / 3600000 * 22)))}px"><div class="tm num">${this._hm(bt)}</div><div class="rail"><i></i></div>`
            + `<div class="bd">${a.e} ${a.t}<small class="num">${sub}</small>${pg}</div>`
            + `<div class="rt num">${Math.round(s0)} → ${Math.round(s1)} %<span class="bat"><i style="left:0;width:${lo}%;background:currentColor;opacity:.35"></i><i style="left:${lo}%;width:${hi - lo}%;background:${a.c}"></i></span></div>${det}</div>`;
        };
        const last = blocks[blocks.length - 1], inDay = sl.filter((x) => x[0] < T1), endSoc = inDay.length ? inDay[inDay.length - 1][1] : last.s1, endT = last.e >= T1 ? '24:00' : this._hm(last.e);
        let tl = '';
        if (!open) {
          const f = cb || next[0] || last, rest = next.filter((b) => b !== f).length;
          h += `<div class="sub tg" data-open>${isToday ? 'Plán batérie' : 'Plán na zajtra'}<span class="chev">${ui('m6 9 6 6 6-6')}</span></div><div class="col" data-open>${row(f)}<div class="more num">${rest ? `+ ${rest} ${rest === 1 ? 'ďalší blok' : rest < 5 ? 'ďalšie bloky' : 'ďalších blokov'} · ` : ''}${endT} SOC ${Math.round(endSoc)} %</div></div>`;
        } else {
        if (past.length) tl += this._past ? past.map(row).join('') + `<div class="done" data-past>▴ skryť</div>` : `<div class="done" data-past>✓ ${past.length} ${past.length === 1 ? 'blok' : past.length < 5 ? 'bloky' : 'blokov'} za nami</div>`;
        tl += next.map(row).join('');
        tl += `<div class="it end" style="--c:transparent"><div class="tm num">${endT}</div><div class="rail"><i style="background:var(--secondary-text-color)"></i></div><div class="bd">${last.e >= T1 ? 'koniec dňa' : 'koniec plánu'} · SOC ${Math.round(endSoc)} %</div><div></div></div>`;
        h += `<div class="sub tg" data-open>${isToday ? 'Plán batérie' : 'Plán na zajtra'}<span class="chev o">${ui('m6 9 6 6 6-6')}</span></div><div>${tl}</div>`;
        }
      } else if (c.plan_entity) h += `<div class="msg">Plán batérie pre tento deň zatiaľ nie je.</div>`;
      if (box.__h !== h) { box.__h = h; box.innerHTML = h; }
    }
  }

  /* ================= Editor ================= */
  class HomePriceCardEditor extends HTMLElement {
    setConfig(c) { this._cfg = Object.assign({}, c); if (this._f) this._f.data = this._data(); }
    _data() { return Object.assign({ title: 'Cena elektriny', unit: '€/MWh' }, this._cfg || {}); }
    set hass(h) {
      this._hass = h;
      if (!this._f) {
        const f = this._f = document.createElement('ha-form');
        const ent = (n, d) => ({ name: n, selector: { entity: d ? { domain: d } : {} } });
        f.schema = [
          { name: 'title', selector: { text: {} } },
          ent('price_entity', 'sensor'), ent('threshold_entity', ['input_number', 'number', 'sensor']),
          { type: 'expandable', name: '', title: 'Plán batérie', icon: 'mdi:robot-outline', expanded: true, schema: [ent('plan_entity', 'sensor'), ent('soc_entity', 'sensor'),
            { name: 'merge', selector: { number: { min: 0, max: 120, step: 15, mode: 'box', unit_of_measurement: 'min' } } }] },
          { name: 'unit', selector: { text: {} } }
        ];
        const L = { title: 'Nadpis', price_entity: 'Ceny (senzor s atribútom ceny)', threshold_entity: 'Prah predaja', plan_entity: 'AI plán (template senzor)', soc_entity: 'SOC batérie', merge: 'Zlúčiť krátke prepnutia do', unit: 'Jednotka ceny' };
        const H = { price_entity: 'Atribút ceny: zoznam {t, p} po 15 min (OKTE).', threshold_entity: 'Ceny nad prahom sú zelené, v prehľade je prerušovaná čiara.', merge: 'Bloky kratšie alebo rovné tomuto času (po 15 min) sa pripoja k susednému a zobrazia ako farebná bodka. 0 = nezlučovať.', plan_entity: 'Senzor sensor.ai_fve_plan – sloty so SOC a akciou.' };
        f.computeLabel = (x) => L[x.name] || x.title || x.name; f.computeHelper = (x) => H[x.name];
        f.addEventListener('value-changed', (e) => {
          e.stopPropagation();
          const v = e.detail.value, c = { type: (this._cfg && this._cfg.type) || 'custom:home-price-card' };
          Object.keys(v).forEach((k) => { if (k === 'type' || v[k] === '' || v[k] == null) return; c[k] = v[k]; });
          if (this._cfg && this._cfg.thresholds) c.thresholds = this._cfg.thresholds.slice();
          this._cfg = c; this.dispatchEvent(new CustomEvent('config-changed', { detail: { config: JSON.parse(JSON.stringify(c)) }, bubbles: true, composed: true }));
        });
        this.appendChild(f);
      }
      this._f.hass = h; this._f.data = this._data();
    }
  }

  // Integrácia načítava kartu cez extra_module_url. Niektoré verzie HA ho spustia skôr, než frontend
  // nainštaluje "scoped custom element registry" – prvky definované vtedy HA nenájde (nekonečné koliesko,
  // "Custom element not found"). Preto definujeme až keď je aplikácia (<home-assistant>) pripravená.
  const register = () => {
    const reg = window.customElements;
    if (!reg.get('home-price-card-editor')) reg.define('home-price-card-editor', HomePriceCardEditor);
    if (!reg.get('home-price-card')) reg.define('home-price-card', HomePriceCard);
  };
  if (window.__haScopedRegistryReady || customElements.get('home-assistant') || !document.querySelector('home-assistant')) {
    register();
  } else {
    let done = false;
    const once = () => { if (!done) { done = true; register(); } };
    customElements.whenDefined('home-assistant').then(() => setTimeout(once, 0));
    setTimeout(once, 10000);
  }
  window.customCards = window.customCards || [];
  if (!window.customCards.some((c) => c.type === 'home-price-card'))
    window.customCards.push({ type: 'home-price-card', name: 'Home Price Card', description: 'Spotové ceny elektriny a plán batérie ako časová os (AI Energy).', preview: false, documentationURL: 'https://github.com/Igypop78/ai-energy' });
  console.info('%c HOME-PRICE-CARD %c ' + VERSION + ' ', 'background:#0a84ff;color:#fff;border-radius:3px 0 0 3px', 'background:#333;color:#fff;border-radius:0 3px 3px 0');
})();
