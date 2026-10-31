/*
 * Igy Battery Action Card + Igy EV Action Card – ovládanie AI Energy priamo z dashboardu.
 * Netreba nič nastavovať – karty si nájdu entity AI Energy samé (pevné entity_id).
 *
 *   type: custom:igy-battery-action-card
 *   type: custom:igy-ev-action-card
 */
(function () {
  'use strict';
  const VERSION = '1.1.3';
  const E = {
    mode: 'sensor.ai_energy_odporucany_rezim', why: 'sensor.ai_energy_dovod', plan: 'sensor.ai_energy_plan',
    minSoc: 'number.ai_energy_min_soc', maxSoc: 'number.ai_energy_max_soc', prah: 'number.ai_energy_prah_predaja',
    chargeKw: 'number.ai_energy_nabijaci_vykon', pvCorr: 'number.ai_energy_korekcia_fve',
    evMode: 'select.ai_energy_auto_rezim', evTime: 'time.ai_energy_auto_cas', evA: 'number.ai_energy_auto_prud',
    evWhy: 'sensor.ai_energy_auto_dovod', evCtl: 'switch.ai_energy_auto_riadenie', evNt: 'switch.ai_energy_auto_nt',
    batMode: 'select.ai_energy_bateria_rezim', batDur: 'select.ai_energy_bateria_rucne_na', batCtl: 'switch.ai_energy_bateria_riadenie',
    evPv: 'switch.ai_energy_auto_fve', evSpot: 'switch.ai_energy_auto_spot', evSpotP: 'number.ai_energy_auto_spot_cena'
  };
  const MODE = {
    predaj: ['Predaj z batérie', '#30d158', '💰'], predaj_fve: ['Predaj len z FVE', '#b4e34f', '🌤️'], nabijanie: ['Nabíjanie zo siete', '#ff453a', '🔋'],
    siet: ['Dom zo siete', '#8e8e93', '⏸️'], bez_pretokov: ['Bez pretokov', '#ffd60a', '🚫'], normal: ['Bežná prevádzka', '#64d2ff', '🏠']
  };
  const ACT = { P: 'predaj z batérie', E: 'predaj len z FVE', N: 'nabíjanie zo siete', F: 'FVE nabíja batériu', O: 'prebytok do siete', G: 'dom zo siete', D: 'dom z batérie' };
  const DUR = [['1h', '1 h'], ['2h', '2 h'], ['4h', '4 h'], ['nt', 'do NT'], ['trvalo', 'natrvalo']];
  const EVM = [['off', 'Vypnuté'], ['now', 'Hneď'], ['time', 'Od času'], ['ai', 'AI']];
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const fmt = (v, d) => Number(v).toLocaleString('sk-SK', { minimumFractionDigits: d, maximumFractionDigits: d });

  const CSS = `
    ha-card { padding: 12px 16px 14px; }
    .hl { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--secondary-text-color); letter-spacing: .02em; }
    .hl ha-icon { --mdc-icon-size: 18px; }
    .pill { margin-left: auto; font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 10px; white-space: nowrap; }
    .box { border-radius: 16px; background: var(--hc-surface, rgba(127,127,127,.1)); padding: 10px 12px; margin-top: 12px; display: flex; gap: 14px; align-items: center; }
    .big { font-size: 26px; font-weight: 700; color: var(--primary-text-color); font-variant-numeric: tabular-nums; line-height: 1.1; }
    .small { font-size: 12px; color: var(--secondary-text-color); }
    .why { font-size: 13px; color: var(--primary-text-color); line-height: 1.35; }
    .why.warn { color: var(--warning-color, #ffb300); }
    .sub { display: flex; font-size: 11px; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .06em; margin: 14px 2px 4px; }
    .sub span { margin-left: auto; text-transform: none; letter-spacing: 0; }
    .row { display: flex; align-items: center; gap: 10px; font-size: 14px; color: var(--primary-text-color); padding: 6px 2px; min-height: 30px; }
    .row .l { flex: 1; } .row .l small { display: block; font-size: 12px; color: var(--secondary-text-color); }
    .row b { font-variant-numeric: tabular-nums; font-weight: 600; }
    .sl { padding: 4px 2px 2px; }
    .sl .row { padding: 0 0 2px; min-height: 0; }
    input[type=range] { -webkit-appearance: none; appearance: none; width: 100%; height: 22px; background: transparent; margin: 0; cursor: pointer; }
    input[type=range]::-webkit-slider-runnable-track { height: 6px; border-radius: 3px; background: linear-gradient(to right, var(--c) var(--p), rgba(127,127,127,.25) var(--p)); }
    input[type=range]::-moz-range-track { height: 6px; border-radius: 3px; background: linear-gradient(to right, var(--c) var(--p), rgba(127,127,127,.25) var(--p)); }
    input[type=range]::-webkit-slider-thumb { -webkit-appearance: none; width: 20px; height: 20px; margin-top: -7px; border-radius: 50%; background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,.4); }
    input[type=range]::-moz-range-thumb { width: 20px; height: 20px; border: 0; border-radius: 50%; background: #fff; box-shadow: 0 1px 4px rgba(0,0,0,.4); }
    .st { display: inline-flex; align-items: center; gap: 6px; }
    .st button { width: 30px; height: 30px; border-radius: 9px; border: 0; background: var(--hc-surface, rgba(127,127,127,.15)); color: var(--primary-text-color); font-size: 17px; cursor: pointer; }
    .st b { min-width: 92px; text-align: center; }
    .seg { display: flex; padding: 3px; gap: 3px; border-radius: 11px; background: var(--hc-surface, rgba(127,127,127,.12)); margin-top: 4px; }
    .seg b { flex: 1; text-align: center; font-size: 13px; font-weight: 500; padding: 7px 0; border-radius: 8px; color: var(--primary-text-color); cursor: pointer; }
    .seg b.on { background: var(--primary-color, #0a84ff); color: var(--text-primary-color, #fff); font-weight: 600; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; padding: 4px 2px; }
    .chip { font-size: 12px; padding: 6px 11px; border-radius: 16px; cursor: pointer; background: var(--hc-surface, rgba(127,127,127,.12)); color: var(--secondary-text-color); border: 1px solid transparent; }
    .chip.on { color: #30d158; background: rgba(48,209,88,.13); border-color: rgba(48,209,88,.45); }
    .tgl { position: relative; width: 44px; height: 26px; border-radius: 13px; background: rgba(127,127,127,.35); cursor: pointer; flex: none; transition: background .15s; }
    .tgl:after { content: ''; position: absolute; top: 3px; left: 3px; width: 20px; height: 20px; border-radius: 50%; background: #fff; transition: left .15s; }
    .tgl.on { background: #30d158; } .tgl.on:after { left: 21px; }
    input[type=time] { font: inherit; font-weight: 600; color: var(--primary-text-color); background: var(--hc-surface, rgba(127,127,127,.15)); border: 0; border-radius: 9px; padding: 5px 10px; }
    .more { font-size: 12px; color: var(--primary-color); cursor: pointer; padding: 6px 2px 0; user-select: none; }
    select.md { font: inherit; font-size: 14px; font-weight: 600; color: var(--primary-text-color); background: var(--hc-surface, rgba(127,127,127,.15)); border: 0; border-radius: 9px; padding: 6px 10px; max-width: 60%; }
    select.md option { color: var(--primary-text-color); background: var(--card-background-color, #1c1c1e); }
    .tag { font-size: 11px; font-weight: 600; padding: 1px 6px; border-radius: 6px; background: rgba(255,159,10,.2); color: #ff9f0a; margin-left: 6px; }
    .msg { font-size: 13px; color: var(--secondary-text-color); padding: 10px 2px 2px; line-height: 1.4; }
  `;

  class Base extends HTMLElement {
    setConfig(c) { this._cfg = Object.assign({}, c || {}); this._sig = ''; if (this._hass) this._render(); }
    set hass(h) { this._hass = h; if (this._busy) return; this._render(); }
    getCardSize() { return 5; }
    getGridOptions() { return { columns: 12, min_columns: 6 }; }
    static getStubConfig() { return {}; }
    _s(id) { return this._hass && this._hass.states[id]; }
    _v(id) { const s = this._s(id); const v = s ? parseFloat(s.state) : NaN; return isNaN(v) ? null : v; }
    _call(domain, service, data) { return this._hass.callService(domain, service, data); }
    _num(id, v) { return this._call('number', 'set_value', { entity_id: id, value: v }); }
    _sw(id, on) { return this._call('switch', on ? 'turn_on' : 'turn_off', { entity_id: id }); }
    _shell(title, icon, pill, body) {
      // ha-card sa vytvorí len raz – témy a card-mod štýlujú práve tento prvok; pri jeho výmene by sa štýl stratil
      if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
      if (!this._card) {
        this.shadowRoot.innerHTML = `<style>${CSS}</style><ha-card><div id="c"></div></ha-card>`;
        this._card = this.shadowRoot.querySelector('ha-card');
      }
      const dark = !!(this._hass.themes && this._hass.themes.darkMode);
      this._card.style.colorScheme = dark ? 'dark' : 'light';
      this.shadowRoot.getElementById('c').innerHTML = `<div class="hl"><ha-icon icon="${icon}"></ha-icon>${esc(this._cfg.title || title)}${pill || ''}</div>${body}`;
      this._wire();
    }
    _slider(id, label, color, unit, fmtv) {
      const s = this._s(id); if (!s) return '';
      const a = s.attributes, v = parseFloat(s.state), mn = a.min ?? 0, mx = a.max ?? 100, st = a.step ?? 1;
      const p = ((v - mn) / (mx - mn)) * 100;
      return `<div class="sl"><div class="row"><span class="l">${label}</span><b data-out="${id}">${fmtv ? fmtv(v) : fmt(v, 0) + ' ' + unit}</b></div>
        <input type="range" data-num="${id}" min="${mn}" max="${mx}" step="${st}" value="${v}" style="--c:${color};--p:${p}%"></div>`;
    }
    _stepper(id, label, hint, step, show) {
      const v = this._v(id); if (v == null) return '';
      return `<div class="row"><span class="l">${label}${hint ? `<small>${hint}</small>` : ''}</span><span class="st"><button data-step="${id}" data-d="${-step}">−</button><b>${show(v)}</b><button data-step="${id}" data-d="${step}">+</button></span></div>`;
    }
    _toggle(id, label, hint) {
      const s = this._s(id); if (!s) return '';
      return `<div class="row"><span class="l">${label}${hint ? `<small>${hint}</small>` : ''}</span><span class="tgl ${s.state === 'on' ? 'on' : ''}" data-sw="${id}"></span></div>`;
    }
    _wire() {
      const r = this.shadowRoot;
      r.querySelectorAll('input[data-num]').forEach((el) => {
        const id = el.dataset.num, out = r.querySelector(`[data-out="${id}"]`), unit = (this._s(id).attributes.unit_of_measurement || '');
        el.addEventListener('pointerdown', () => { this._busy = true; });
        el.addEventListener('input', () => {
          const p = ((el.value - el.min) / (el.max - el.min)) * 100; el.style.setProperty('--p', p + '%');
          if (out) out.textContent = (this._fmtOut && this._fmtOut[id]) ? this._fmtOut[id](parseFloat(el.value)) : fmt(el.value, 0) + ' ' + unit;
        });
        el.addEventListener('change', () => { this._busy = false; this._num(id, parseFloat(el.value)); });
        el.addEventListener('pointerup', () => setTimeout(() => { this._busy = false; }, 300));
      });
      r.querySelectorAll('[data-step]').forEach((el) => el.addEventListener('click', () => {
        const id = el.dataset.step, s = this._s(id), v = parseFloat(s.state) + parseFloat(el.dataset.d);
        this._num(id, Math.min(s.attributes.max ?? 1e9, Math.max(s.attributes.min ?? -1e9, Math.round(v * 1000) / 1000)));
      }));
      r.querySelectorAll('[data-sw]').forEach((el) => el.addEventListener('click', () => this._sw(el.dataset.sw, !el.classList.contains('on'))));
      r.querySelectorAll('[data-more]').forEach((el) => el.addEventListener('click', () => { this._more = !this._more; this._sig = ''; this._render(); }));
      if (this._wireExtra) this._wireExtra(r);
    }
    _changed(ids) {
      const sig = ids.map((id) => { const s = this._s(id); return s ? s.last_updated + s.state : '-'; }).join('|') + '|' + this._more + '|' + !!(this._hass.themes && this._hass.themes.darkMode);
      if (sig === this._sig) return false; this._sig = sig; return true;
    }
  }

  // ------------------------------------------------------------------ batéria
  class IgyBatteryActionCard extends Base {
    _render() {
      if (!this._hass || !this._cfg) return;
      if (!this._changed([E.mode, E.why, E.plan, E.minSoc, E.maxSoc, E.prah, E.chargeKw, E.pvCorr, E.batMode, E.batDur, E.batCtl])) return;
      const m = this._s(E.mode);
      if (!m) { this._shell('Batéria', 'mdi:home-battery', '', '<div class="msg">Nenašiel som AI Energy. Nainštaluj a nastav integráciu AI Energy.</div>'); return; }
      const ap = m.attributes.aplikovany_rezim || m.state, man = !!m.attributes.rucne;
      const [mt, mc, me] = MODE[ap] || [ap, '#8e8e93', ''];
      const pill = `<span class="pill" style="background:${mc}26;color:${mc}">${me} ${esc(mt)}${man ? ' · ručne' : ''}</span>`;
      const pl = this._s(E.plan), pa = pl ? pl.attributes : {}, soc = pa.soc, sl = pa.sloty || [];
      let next = '';
      if (sl.length) {
        const k = sl.findIndex((x) => x[2] !== sl[0][2]);
        if (k > 0) { const d = new Date(sl[k][0] * 1000); next = `ďalej ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')} ${ACT[sl[k][2]] || ''}`; }
      }
      const minS = this._v(E.minSoc);
      const box = `<div class="box"><div><div class="big">${soc != null ? fmt(soc, 0) + ' %' : '–'}</div><div class="small">batéria${minS != null ? ' · min ' + fmt(minS, 0) + ' %' : ''}</div></div>
        <div style="flex:1;min-width:0"><div class="why">${esc((this._s(E.why) || {}).state || '')}</div>${next ? `<div class="small">${esc(next)}</div>` : ''}</div></div>`;
      const kwh = (v) => fmt(v / 1000, 3) + ' €/kWh';
      let body = box;
      const bm = this._s(E.batMode);
      if (bm) {
        const ctl = (this._s(E.batCtl) || {}).state === 'on';
        const opts = [['auto', 'Auto (AI)']].concat(Object.keys(MODE).map((k) => [k, MODE[k][0]]));
        let until = '';
        if (bm.state !== 'auto') {
          const u = bm.attributes.rucne_do; const d = u ? new Date(u) : null;
          until = d ? `do ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}` : 'natrvalo';
        }
        body += `<div class="sub">Menič${bm.state !== 'auto' ? `<span>ručne ${esc(until)}</span>` : ''}</div>`
          + `<div class="row"><span class="l">Režim</span><select class="md" data-batmode>${opts.map(([k, t]) => `<option value="${k}" ${k === bm.state ? 'selected' : ''}>${t}</option>`).join('')}</select></div>`;
        const dur = (this._s(E.batDur) || {}).state;
        body += `<div class="row"><span class="l">Ručný režim na<small>po uplynutí sa vráti na Auto</small></span></div><div class="chips" style="margin-top:-4px">${DUR.map(([k, t]) => `<span class="chip ${k === dur ? 'on' : ''}" data-dur="${k}">${t}</span>`).join('')}</div>`;
        body += this._toggle(E.batCtl, '<b>Riadiť menič</b>', ctl ? 'AI Energy posiela režim do meniča' : 'vypnuté = len odporúča, nič neprepína');
      }
      body += `<div class="sub">Nastavenia</div>`
        + this._slider(E.minSoc, 'Min SOC', '#64d2ff', '%')
        + this._slider(E.maxSoc, 'Max SOC nabíjania zo siete', '#ff453a', '%')
        + this._stepper(E.prah, 'Min. predajná cena', this._prahHint(pa), 5, kwh)
        + `<div class="more" data-more>${this._more ? '▾' : '▸'} Pokročilé</div>`;
      if (this._more) {
        body += this._stepper(E.chargeKw, 'Nabíjací výkon zo siete', '', 0.5, (v) => fmt(v, 1) + ' kW')
          + this._slider(E.pvCorr, 'Korekcia predpovede FVE', '#ffc53d', '%');
      }
      this._shell('Batéria', 'mdi:home-battery', pill, body);
    }
  }

  // či min. predajná cena práve niečo mení: predaj v okne určuje aj množstvo energie (top N najdrahších úsekov)
  IgyBatteryActionCard.prototype._prahHint = function (pa) {
    const prah = this._v(E.prah), now = Date.now() / 1000;
    const w = (pa.okna || []).find((x) => x.od <= now && now < x.do);
    if (prah == null || !w) return 'pod ňou sa z batérie nepredáva';
    const k = (v) => fmt(v / 1000, 3);
    if (!w.hranica) return `v tomto okne nie je nič na predaj nad ${k(prah)} €/kWh`;
    if (w.hranica > prah + 0.5) return `teraz nič nemení – predáva sa od ${k(w.hranica)} €/kWh (energie je menej než drahých úsekov)`;
    return 'teraz obmedzuje predaj – lacnejšie úseky sa nepredajú';
  };

  IgyBatteryActionCard.prototype._wireExtra = function (r) {
    const sel = r.querySelector('[data-batmode]');
    if (sel) {
      sel.addEventListener('focus', () => { this._busy = true; });
      sel.addEventListener('blur', () => { this._busy = false; });
      sel.addEventListener('change', () => { this._busy = false; this._call('select', 'select_option', { entity_id: E.batMode, option: sel.value }); });
    }
    r.querySelectorAll('[data-dur]').forEach((el) => el.addEventListener('click', async () => {
      await this._call('select', 'select_option', { entity_id: E.batDur, option: el.dataset.dur });
      const bm = this._s(E.batMode);
      if (bm && bm.state !== 'auto') this._call('select', 'select_option', { entity_id: E.batMode, option: bm.state }); // prepočíta koniec
    }));
  };

  // ------------------------------------------------------------------ auto
  class IgyEvActionCard extends Base {
    _render() {
      if (!this._hass || !this._cfg) return;
      if (!this._changed([E.evMode, E.evTime, E.evA, E.evWhy, E.evCtl, E.evNt, E.evPv, E.evSpot, E.evSpotP])) return;
      const sel = this._s(E.evMode), why = this._s(E.evWhy);
      if (!sel || !why) { this._shell('Auto', 'mdi:car-electric', '', '<div class="msg">Nabíjanie auta nie je nastavené. V AI Energy → Konfigurovať zapni „Mám nabíjačku auta“.</div>'); return; }
      const a = why.attributes, mode = sel.state, ctl = (this._s(E.evCtl) || {}).state === 'on';
      const ph = a.fazy || 3, kw = (amp) => fmt(amp * 230 * ph / 1000, 1);
      const pill = a.nabija ? '<span class="pill" style="background:#30d15826;color:#30d158">⚡ nabíja</span>'
        : a.pripojene === false ? '<span class="pill" style="background:rgba(127,127,127,.18);color:var(--secondary-text-color)">odpojené</span>'
        : '<span class="pill" style="background:#0a84ff26;color:#4da3ff">🔌 pripojené</span>';
      this._fmtOut = { [E.evA]: (v) => `${fmt(v, 0)} A · ${kw(v)} kW` };
      let body = `<div class="seg">${EVM.map(([k, t]) => `<b data-mode="${k}" class="${k === mode ? 'on' : ''}">${t}</b>`).join('')}</div>`;
      if (mode === 'time') {
        const t = (this._s(E.evTime) || {}).state || '';
        body += `<div class="row"><span class="l">Začať o</span><input type="time" data-time value="${esc(t.slice(0, 5))}"></div>`;
      }
      if (mode === 'now' || mode === 'time') body += this._slider(E.evA, 'Prúd', '#0a84ff', 'A', this._fmtOut[E.evA]);
      if (mode === 'ai') {
        const on = (id) => (this._s(id) || {}).state === 'on';
        body += `<div class="chips">${[[E.evNt, 'Nízka tarifa'], [E.evPv, 'Prebytky FVE'], [E.evSpot, 'Lacný spot']].map(([id, t]) => `<span class="chip ${on(id) ? 'on' : ''}" data-chip="${id}">${on(id) ? '✓ ' : ''}${t}</span>`).join('')}</div>`;
        if (on(E.evSpot)) body += this._stepper(E.evSpotP, 'Lacný spot do', 'nabíja, keď je spot pod touto cenou', 5, (v) => fmt(v / 1000, 3) + ' €/kWh');
      }
      const txt = (why.state || '').replace(/^Len odporúčanie \(Riadenie vypnuté\) – /, '');
      body += `<div class="why ${ctl ? '' : 'warn'}" style="padding:8px 2px 2px">${ctl ? '' : '⚠️ Len odporúčanie – '}${esc(txt)}</div>`;
      body += this._toggle(E.evCtl, '<b>Riadiť nabíjačku</b>', 'vypnuté = len odporúča, nič neprepína');
      this._shell('Auto', 'mdi:car-electric', pill, body);
    }
    _wireExtra(r) {
      r.querySelectorAll('[data-mode]').forEach((el) => el.addEventListener('click', () => this._call('select', 'select_option', { entity_id: E.evMode, option: el.dataset.mode })));
      r.querySelectorAll('[data-chip]').forEach((el) => el.addEventListener('click', () => this._sw(el.dataset.chip, !el.classList.contains('on'))));
      const t = r.querySelector('[data-time]');
      if (t) {
        t.addEventListener('focus', () => { this._busy = true; });
        t.addEventListener('blur', () => { this._busy = false; });
        t.addEventListener('change', () => { if (t.value) this._call('time', 'set_value', { entity_id: E.evTime, time: t.value + ':00' }); });
      }
    }
  }

  // registrácia až keď je HA frontend pripravený (rovnako ako Igy Price Action Card)
  const register = () => {
    const reg = window.customElements;
    if (!reg.get('igy-battery-action-card')) reg.define('igy-battery-action-card', IgyBatteryActionCard);
    if (!reg.get('igy-ev-action-card')) reg.define('igy-ev-action-card', IgyEvActionCard);
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
  [['igy-battery-action-card', 'Igy Battery Action Card', 'Batéria: odporúčaný režim, min/max SOC, min. predajná cena (AI Energy).'],
   ['igy-ev-action-card', 'Igy EV Action Card', 'Nabíjanie auta: režim, čas, prúd, zdroje pre AI a riadenie (AI Energy).']].forEach(([type, name, description]) => {
    if (!window.customCards.some((c) => c.type === type)) window.customCards.push({ type, name, description, preview: true, documentationURL: 'https://github.com/Igypop78/ai-energy' });
  });
  console.info('%c IGY-ACTION-CARDS %c ' + VERSION + ' ', 'background:#30d158;color:#000;border-radius:3px 0 0 3px', 'background:#333;color:#fff;border-radius:0 3px 3px 0');
})();
