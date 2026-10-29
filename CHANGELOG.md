# Zmeny

Formát podľa [Keep a Changelog](https://keepachangelog.com/sk/1.1.0/), verzie podľa [SemVer](https://semver.org/lang/sk/).

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
