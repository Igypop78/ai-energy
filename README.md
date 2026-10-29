# AI Energy

Integrácia pre [Home Assistant](https://www.home-assistant.io/), ktorá plánuje nabíjanie a predaj z domácej batérie
podľa spotových cien elektriny (OKTE a ďalšie) a dvojtarifného nákupu – s dôrazom na to, aby si **vždy videl,
čo sa deje a prečo**.

> ⚠️ **Vo vývoji (v0.1).** Táto verzia zatiaľ **nič neriadi** – zbiera ceny, drží ich zálohu a ukazuje tarifu.
> Plánovač a riadenie meniča pribudnú v ďalších verziách.

## Čo vie v0.1

| Entita | Popis |
|---|---|
| `sensor.ai_energy_ceny` | Ceny dnes + zajtra po 15 min (atribút `ceny`). **Záloha** – pri výpadku zdroja aj po reštarte HA ostanú posledné ceny. |
| `sensor.ai_energy_aktualna_cena` | Spotová cena aktuálneho 15-min slotu (€/MWh). |
| `binary_sensor.ai_energy_nizka_tarifa` | Zapnutý počas nízkej tarify (NT). |

Podporované zdroje cien: integrácia **OKTE** (`period_data`) a bežné formáty iných integrácií
(napr. Nord Pool `raw_today` / `raw_tomorrow`).

## Inštalácia cez HACS

1. HACS → **⋮ → Vlastné repozitáre** (Custom repositories).
2. URL: `https://github.com/Igypop78/ai-energy`, kategória **Integration** → Pridať.
3. Nájdi **AI Energy** → Stiahnuť → **reštartuj Home Assistant**.
4. **Nastavenia → Zariadenia a služby → Pridať integráciu → AI Energy**.

## Nastavenie

Sprievodca má dva kroky:

1. **Spotové ceny** – senzor s dnešnými cenami (povinný) a so zajtrajšími (voliteľný).
   Integrácia OKTE sa nájde automaticky.
2. **Tarifa nákupu** – časy nízkej tarify a ceny vrátane distribúcie.
   Predvolené hodnoty = ZSE DD3 s dodatkom pre elektromobily:
   - NT: `23:45-05:45, 13:45-15:45`
   - NT 120 €/MWh, VT 210 €/MWh
   - poplatok za predaj 15 €/MWh (výkupca strháva zo spotu)

Všetko sa dá neskôr zmeniť: **Nastavenia → Zariadenia a služby → AI Energy → Konfigurovať**.

## Plán vývoja

- [x] Záloha cien, aktuálna cena, nízka tarifa
- [ ] Plánovač batérie (predaj v najdrahších slotoch, nabíjanie v NT, predpoveď FVE)
- [ ] Karta s cenami a plánom (Home Price Card) – inštaluje sa spolu s integráciou
- [ ] Riadenie meniča (Deye / Solarman), suchý beh a ručný override
- [ ] Nabíjanie auta (SmartEVSE), limity ističa
- [ ] Ďalšie meniče a tarify

## Licencia

MIT
