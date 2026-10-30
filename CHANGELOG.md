# Zmeny

Formát podľa [Keep a Changelog](https://keepachangelog.com/sk/1.1.0/), verzie podľa [SemVer](https://semver.org/lang/sk/).

## [0.6.0] – 2026-10-30

### Pridané
- **Ovládanie meniča** (nový krok sprievodcu): AI Energy zapisuje režim batérie do tvojho výberu (napr.
  `input_select.deye_operation_mode`); v ďalšom kroku priradíš každému režimu AI Energy možnosť z výberu
  (Predaj z batérie → Export from Battery, …). Samotný menič nastavuje tvoja automatizácia.
- `switch.ai_energy_bateria_riadenie` – predvolene **vypnuté** (len odporúča).
- **Ručný režim** `select.ai_energy_bateria_rezim` (Auto / konkrétny režim) na `select.ai_energy_bateria_rucne_na`
  (1 h, 2 h, 4 h, do ďalšej NT, natrvalo) – potom sa vráti na Auto.
- Voliteľne **nabíjací prúd zo siete** (A): podľa nabíjacieho výkonu, spoločného kábla s autom (batéria má prednosť)
  a ističa; zníženie hneď, zvýšenie o ≥ 10 A najskôr po 2 min.
- `sensor.ai_energy_odporucany_rezim` má atribúty `aplikovany_rezim`, `rucne`, `rucne_do`.
- Igy Battery Action Card: sekcia **Menič** – režim (Auto / ručne), na ako dlho, Riadiť menič.

## [0.5.0] – 2026-10-29

### Pridané
- **Igy Battery Action Card** (`custom:igy-battery-action-card`) – odporúčaný režim, SOC a dôvod, čo príde ďalej;
  posuvníky min/max SOC, min. predajná cena v €/kWh, v *Pokročilých* nabíjací výkon a korekcia FVE.
- **Igy EV Action Card** (`custom:igy-ev-action-card`) – režim nabíjania (Vypnuté / Hneď / Od času / AI), čas štartu,
  prúd (A aj kW), zdroje pre AI ako štítky (NT, prebytky FVE, lacný spot), Riadiť nabíjačku, dôvod.
- Obe karty sa inštalujú s integráciou a netreba ich nastavovať – entity AI Energy si nájdu samé.
- `sensor.ai_energy_auto_dovod` má atribút `fazy`.

## [0.4.1] – 2026-10-29

### Opravené
- Nedokončený (zavretý) sprievodca už neblokuje spustenie nového („This is already being configured“).

## [0.4.0] – 2026-10-29

### Pridané
- **Nový sprievodca** krok po kroku s vysvetlením pri každom poli: Vitaj (čo treba mať, čo mám doma) → Ceny → Nákup →
  Predaj → Batéria a spotreba → FVE → Nabíjačka auta → Istič a elektromer → Hotovo (zhrnutie).
  Kroky pre FVE a auto sa zobrazia len tomu, kto ich má. Konfigurovať = ponuka s rovnakými časťami.
- **Predaj elektriny**: spotová cena mínus poplatok, **pevná výkupná cena** (voliteľne pásmo s inou cenou) alebo **nepredávam**.
  Plánovač počíta s cenou predaja po 15-min úsekoch.
- **Jedna tarifa** (bez NT) – plán ide po dňoch, bez nabíjania zo siete.
- **Spotreba domu v kWh/deň** + voliteľný senzor (energia alebo výkon) – priemer z histórie za 7 dní.
- **Istič v ampéroch** (+ rezerva %, predvolene 10 %); režimy nabíjačky typu select sa vyberajú zo zoznamu.
- Ceny v sprievodcovi v **€/kWh**.
- Nová ikona integrácie (spotové ceny).
- Testy sprievodcu a načítania integrácie v Home Assistant (GitHub Actions).

### Zmenené
- „Spotreba domu teraz“ zrušená – používa sa senzor spotreby domu (ak je výkonový) alebo elektromer.
- Pokročilé polia (min/max prúd, rezerva ističa, spoločný limit, záporný odber) sú v zbalenej sekcii *Pokročilé*.

### Poznámky
- Pri prechode z 0.3 zostávajú nastavenia; staré „Spotreba domu (kW)“ a „Limit odberu (kW)“ platia, kým ich neprepíšeš
  v Konfigurovať (Batéria a spotreba / Istič a elektromer).
- Pri zmene spôsobu predaja skontroluj **Min. predajnú cenu** – drží si poslednú nastavenú hodnotu.

## [0.3.1] – 2026-10-29

### Pridané
- Ikona integrácie (`brand/icon.png`) – zobrazí sa od Home Assistant 2026.3.

### Zmenené
- Nabíjanie auta: pri prepínači typu select sa možnosti „nabíjaj“ / „vypni“ predvyplnia už vo formulári
  (SmartEVSE: Normal / Off).

## [0.3.0] – 2026-10-29

### Pridané
- **Nabíjanie auta** – nový (voliteľný) krok sprievodcu: prepínač nabíjačky (switch / select), prúd, fázy,
  min/max prúd, stav auta, meranie odberu zo siete, limit ističa a spoločný limit batérie + auta.
  SmartEVSE sa predvyplní automaticky.
- Režimy `select.ai_energy_auto_rezim`: Vypnuté, Nabíjať hneď, Nabíjať od času (`time.ai_energy_auto_cas`), AI.
- AI: nabíjanie v NT (prúd podľa ističa, batéria má na kábli prednosť), z prebytku FVE (2 min štart / 3 min stop),
  voliteľne pri lacnom spote.
- `switch.ai_energy_auto_riadenie` – vypnuté = len odporúča; `sensor.ai_energy_auto_dovod` – čo a prečo.
- Nastavenia integrácie (Konfigurovať) rozdelené do ponuky: Ceny a tarifa / Batéria a FVE / Nabíjanie auta.

### Zmenené
- Karta premenovaná na **Igy Price Action Card** (`custom:igy-price-action-card`, verzia 3.0.0).
  Staré `custom:home-price-card` funguje ďalej.

## [0.2.3] – 2026-10-29

### Opravené
- Home Price Card berie aktuálne SOC z entity nastavenej v AI Energy (atribút `soc_entity` plánu),
  nie z prvého nájdeného senzora batérie.

## [0.2.2] – 2026-10-29

### Opravené
- Home Price Card: v zozname kariet sa nekonečne točilo koliesko a v konzole bola chyba
  „Custom element not found: home-price-card“. Karta sa načítala skôr, než HA pripravil register prvkov,
  teraz sa zaregistruje až po štarte aplikácie.

## [0.2.1] – 2026-10-29

### Opravené
- Home Price Card: v zozname kariet sa namiesto nekonečne točiaceho náhľadu zobrazí dlaždica s popisom.

## [0.2.0] – 2026-10-29

### Pridané
- **Plánovač batérie** (`planner.py`): predaj v najdrahších 15-min slotoch okna (predajná hranica), nabíjanie v NT
  len na potrebný cieľ, prenos zostatku energie do ďalšieho okna, nočná arbitráž s kontrolou dobitia na ranný cieľ.
- Okná plánu sa odvodzujú z nastavených intervalov NT – funguje aj pre iné tarify než ZSE DD3.
- Predaj z batérie nikdy pod min SOC; pri batérii na minime a prebytku FVE odporúča predaj len z FVE (Export Now).
- Predpoveď FVE zo Solcastu (`detailedForecast`) s nastaviteľnou korekciou.
- Sprievodca: nový krok **Batéria a FVE** (SOC, kapacita, výkon nabíjania a predaja, spotreba domu, voliteľne Solcast a merania).
- Entity: `sensor.ai_energy_plan`, `sensor.ai_energy_odporucany_rezim`, `sensor.ai_energy_dovod`,
  `sensor.ai_energy_predajna_hranica`, `sensor.ai_energy_ciel_nt`.
- Nastavenia ako entity (`number.ai_energy_*`): min. predajná cena (predvolene z tarify), min SOC, max SOC nabíjania zo siete,
  nabíjací výkon, korekcia FVE – zmena sa hneď prejaví v pláne.
- **Home Price Card** sa registruje automaticky spolu s integráciou (netreba kopírovať súbory ani pridávať zdroj).
- Testy plánovača.

### Poznámky
- Integrácia zatiaľ **len odporúča**, nič neprepína.
- Po aktualizácii z 0.1.0 doplň batériu cez **Nastavenia → Zariadenia a služby → AI Energy → Konfigurovať**
  (inak plán hlási „Chýba SOC batérie“).

## [0.1.0] – 2026-10-29

### Pridané
- Sprievodca nastavením: zdroj spotových cien (OKTE, Nord Pool) a tarifa nákupu (predvolene ZSE DD3).
- Záloha cien dnes + zajtra – prežije výpadok zdroja aj reštart HA (`sensor.ai_energy_ceny`).
- `sensor.ai_energy_aktualna_cena`, `binary_sensor.ai_energy_nizka_tarifa`.
- Preklady sk/en, kontrola HACS a hassfest na GitHube.
