# AI Energy

Integrácia pre [Home Assistant](https://www.home-assistant.io/), ktorá plánuje nabíjanie a predaj z domácej batérie
podľa spotových cien elektriny (OKTE a ďalšie) a dvojtarifného nákupu – s dôrazom na to, aby si **vždy videl,
čo sa deje a prečo**.

> ⚠️ **Vo vývoji (v0.2).** Integrácia zatiaľ **len odporúča** – vypočíta plán a odporúčaný režim,
> ale nič neprepína. Riadenie meniča pribudne v ďalšej verzii.

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

### Karta Home Price Card

Karta sa nainštaluje **spolu s integráciou**. Na dashboarde: **Pridať kartu → Home Price Card**
– entity sa doplnia samé. Ukazuje ceny, predajnú hranicu a plán batérie ako časovú os.

## Inštalácia cez HACS

1. HACS → **⋮ → Vlastné repozitáre** (Custom repositories).
2. URL: `https://github.com/Igypop78/ai-energy`, kategória **Integration** → Pridať.
3. Nájdi **AI Energy** → Stiahnuť → **reštartuj Home Assistant**.
4. **Nastavenia → Zariadenia a služby → Pridať integráciu → AI Energy**.

## Nastavenie

Sprievodca má tri kroky:

1. **Spotové ceny** – senzor s dnešnými cenami (povinný) a so zajtrajšími (voliteľný).
   Integrácia OKTE sa nájde automaticky.
2. **Tarifa nákupu** – časy nízkej tarify a ceny vrátane distribúcie.
   Predvolené hodnoty = ZSE DD3 s dodatkom pre elektromobily:
   - NT: `23:45-05:45, 13:45-15:45`
   - NT 120 €/MWh, VT 210 €/MWh
   - poplatok za predaj 15 €/MWh (výkupca strháva zo spotu)

3. **Batéria a FVE** – senzor SOC, kapacita, výkon nabíjania zo siete a predaja,
   voliteľne predpoveď FVE (Solcast) a merania výkonu FVE a spotreby.

Všetko sa dá neskôr zmeniť: **Nastavenia → Zariadenia a služby → AI Energy → Konfigurovať**.

## Plán vývoja

- [x] Záloha cien, aktuálna cena, nízka tarifa
- [x] Plánovač batérie (predaj v najdrahších slotoch, nabíjanie v NT, predpoveď FVE)
- [x] Karta s cenami a plánom (Home Price Card) – inštaluje sa spolu s integráciou
- [ ] Riadenie meniča (Deye / Solarman), suchý beh a ručný override
- [ ] Nabíjanie auta (SmartEVSE), limity ističa
- [ ] Ďalšie meniče a tarify

## Vyskúšanie bez batérie (testovacia inštalácia)

Vytvor si pomocníka **Nastavenia → Zariadenia a služby → Pomocníci → Vytvoriť → Číslo**:
názov *Sim SOC*, 0–100, krok 1, jednotka %. V 3. kroku sprievodcu ho vyber ako **SOC batérie**.
Posúvaním hodnoty uvidíš, ako sa mení plán a odporúčaný režim.

## Licencia

MIT
