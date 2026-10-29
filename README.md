# AI Energy

Integrácia pre [Home Assistant](https://www.home-assistant.io/), ktorá plánuje nabíjanie a predaj z domácej batérie
podľa spotových cien elektriny (OKTE a ďalšie) a dvojtarifného nákupu – s dôrazom na to, aby si **vždy videl,
čo sa deje a prečo**.

> ⚠️ **Vo vývoji (v0.3).** Batériu zatiaľ **len odporúča** (riadenie meniča pribudne neskôr).
> **Nabíjanie auta už vie riadiť** – po zapnutí prepínača *Auto – riadenie*.

## Čo vie

**Ceny a tarifa**

| Entita | Popis |
|---|---|
| `sensor.ai_energy_ceny` | Ceny dnes + zajtra po 15 min (atribút `ceny`). **Záloha** – pri výpadku zdroja aj po reštarte HA ostanú posledné ceny. |
| `sensor.ai_energy_aktualna_cena` | Spotová cena aktuálneho 15-min slotu (€/MWh). |
| `binary_sensor.ai_energy_nizka_tarifa` | Zapnutý počas nízkej tarify (NT). |

**Plán batérie**

| Entita | Popis |
|---|---|
| `sensor.ai_energy_odporucany_rezim` | Čo robiť práve teraz: predaj z batérie, predaj len z FVE, nabíjanie zo siete, dom zo siete, bez pretokov, bežná prevádzka. |
| `sensor.ai_energy_dovod` | Prečo – napr. *„Predaj 287 € ≥ hranica 281 € (ráno do 13:45, SOC 64 % / min 20 %)“*. |
| `sensor.ai_energy_plan` | Plán po 15 min (SOC a akcia), súčty: predaj, tržba, nákup v NT. |
| `sensor.ai_energy_predajna_hranica` | Od akej ceny sa v aktuálnom okne predáva. |
| `sensor.ai_energy_ciel_nt` | Na koľko % sa batéria nabije v najbližšej NT. |

**Nastavenia priamo z dashboardu** (zariadenie AI Energy → Konfigurácia): min. predajná cena,
min SOC, max SOC nabíjania zo siete, nabíjací výkon, korekcia predpovede FVE. Zmena sa hneď prejaví v pláne.

### Ako plánuje

- Deň sa delí na **okná** podľa nízkej tarify. V každom okne sa batéria predá v **najdrahších 15-min slotoch**
  – toľkých, koľko energie bude k dispozícii (predajná hranica).
- V NT sa nabije len **toľko, koľko treba** na predaje v ďalšom okne (mínus slnko, ktoré príde pred nimi).
- Energia, ktorá v okne ostane, sa **prenáša** do ďalšieho okna.
- V noci sa predá aj drahý slot, ak sa batéria potom **stihne dobiť** na ranný cieľ.
- Z batérie sa **nikdy nepredáva pod min SOC**. Keď je batéria na minime a svieti slnko, predáva sa **len FVE**.
- Predvolená **min. predajná cena** = poplatok za predaj + cena NT so stratami + opotrebenie (45 €/MWh) + zisk (40 €/MWh).

**Nabíjanie auta** (voliteľné, 4. krok sprievodcu)

| Entita | Popis |
|---|---|
| `select.ai_energy_auto_rezim` | **Vypnuté** / **Nabíjať hneď** / **Nabíjať od času** / **AI**. |
| `time.ai_energy_auto_cas` | Kedy začať v režime *Nabíjať od času*. |
| `number.ai_energy_auto_prud` | Prúd pre ručné režimy (Nabíjať hneď, od času). |
| `switch.ai_energy_auto_riadenie` | **Vypnuté = len odporúča** (nič neprepína), zapnuté = nastavuje nabíjačku. |
| `sensor.ai_energy_auto_dovod` | Čo nabíjanie robí a prečo, napr. *„AI: prebytok FVE 5.2 kW – 7 A (4.8 kW)“*. |
| `switch.ai_energy_auto_nt` / `_fve` / `_spot`, `number.ai_energy_auto_spot_cena` | Z čoho smie nabíjať režim AI. |

Režimy:

- **Nabíjať hneď** – nabíja nastaveným prúdom.
- **Nabíjať od času** – v nastavený čas začne; po dobití (10 min bez nabíjania) alebo odpojení auta skončí.
- **AI** – nabíja
  - v **nízkej tarife** plným prúdom, ktorý dovolí istič (a spoločný kábel s batériou – batéria má prednosť),
  - z **prebytku FVE** – prúd sa prispôsobuje prebytku; zapne sa, keď prebytok vydrží 2 min, vypne, keď 3 min chýba;
    nepoužije sa, keď plán batérie práve predáva (vtedy je predaj výhodnejší),
  - pri **lacnom spote** (voliteľné, predvolene vypnuté) – keď je spotová cena nižšia ako nastavená hranica.
    Má zmysel pri nákupe za spotovú cenu; pri pevnej tarife (napr. ZSE DD3) platíš aj tak NT/VT.

Funguje s nabíjačkami, ktoré majú v HA prepínač (switch alebo select) a voliteľne prúd (number).
SmartEVSE sa predvyplní sám (`select.smartevse_mode` Normal/Off, `number.smartevse_chargecurrentoverride`).

### Karta Igy Price Action Card

Karta sa nainštaluje **spolu s integráciou**. Na dashboarde: **Pridať kartu → Igy Price Action Card**
– entity sa doplnia samé. Ukazuje ceny, predajnú hranicu a plán batérie ako časovú os.
(Staršie dashboardy s `type: custom:home-price-card` fungujú ďalej.)

## Inštalácia cez HACS

1. HACS → **⋮ → Vlastné repozitáre** (Custom repositories).
2. URL: `https://github.com/Igypop78/ai-energy`, kategória **Integration** → Pridať.
3. Nájdi **AI Energy** → Stiahnuť → **reštartuj Home Assistant**.
4. **Nastavenia → Zariadenia a služby → Pridať integráciu → AI Energy**.

## Nastavenie

Sprievodca má štyri kroky:

1. **Spotové ceny** – senzor s dnešnými cenami (povinný) a so zajtrajšími (voliteľný).
   Integrácia OKTE sa nájde automaticky.
2. **Tarifa nákupu** – časy nízkej tarify a ceny vrátane distribúcie.
   Predvolené hodnoty = ZSE DD3 s dodatkom pre elektromobily:
   - NT: `23:45-05:45, 13:45-15:45`
   - NT 120 €/MWh, VT 210 €/MWh
   - poplatok za predaj 15 €/MWh (výkupca strháva zo spotu)

3. **Batéria a FVE** – senzor SOC, kapacita, výkon nabíjania zo siete a predaja,
   voliteľne predpoveď FVE (Solcast) a merania výkonu FVE a spotreby.
4. **Nabíjanie auta** – voliteľné. Prepínač nabíjačky, prúd, fázy, min/max prúd, stav auta,
   meranie odberu zo siete (odporúčané – prebytky FVE a istič) a limity ističa / spoločného kábla.

Všetko sa dá neskôr zmeniť: **Nastavenia → Zariadenia a služby → AI Energy → Konfigurovať** (ceny a tarifa / batéria a FVE / nabíjanie auta).

## Plán vývoja

- [x] Záloha cien, aktuálna cena, nízka tarifa
- [x] Plánovač batérie (predaj v najdrahších slotoch, nabíjanie v NT, predpoveď FVE)
- [x] Karta s cenami a plánom (Igy Price Action Card) – inštaluje sa spolu s integráciou
- [x] Nabíjanie auta (NT, prebytky FVE, lacný spot, od času), limity ističa a kábla
- [ ] Riadenie meniča (skripty + blueprint pre Deye / Solarman), ručný override
- [ ] Ďalšie meniče a tarify

## Vyskúšanie bez batérie (testovacia inštalácia)

Vytvor si pomocníka **Nastavenia → Zariadenia a služby → Pomocníci → Vytvoriť → Číslo**:
názov *Sim SOC*, 0–100, krok 1, jednotka %. V 3. kroku sprievodcu ho vyber ako **SOC batérie**.
Posúvaním hodnoty uvidíš, ako sa mení plán a odporúčaný režim.

## Licencia

MIT
