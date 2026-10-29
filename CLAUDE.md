# AI Energy – poznámky pre vývoj

- Integrácia pre Home Assistant (`custom_components/ai_energy`), distribúcia cez HACS.
- Cieľ: jednoduché pre bežných ľudí – rozumné predvoľby, krátky sprievodca, pokročilé veci skryté.
- UI texty a README po slovensky; preklady v `translations/sk.json` a `translations/en.json`
  (`strings.json` = angličtina, musí byť zhodný s `translations/en.json`).
- Čistá logika bez závislosti na HA patrí do samostatných modulov (napr. `prices.py`), aby sa dala testovať
  pytestom bez inštalácie Home Assistant (`tests/`).
- Minimálna verzia HA: 2025.1 (`hacs.json`).
- Pri zmene správania zvýš `version` v `manifest.json`.
