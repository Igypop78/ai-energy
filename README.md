# AI Energy

Integrácia pre [Home Assistant](https://www.home-assistant.io/), ktorá plánuje nabíjanie a predaj z domácej batérie
podľa spotových cien elektriny (OKTE a ďalšie) a dvojtarifného nákupu – s dôrazom na to, aby si **vždy videl,
čo sa deje a prečo**.

> ⚠️ **Vo vývoji.** Batériu riadi cez tvoj výber režimu meniča (po zapnutí *Batéria – riadenie*),
> nabíjanie auta po zapnutí *Auto – riadenie*. Predvolene obe len odporúčajú.

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
- V NT sa nabije len **toľko, koľko treba** na predaje v ďalšom okne a – ak je to lacnejšie ako vysoká tarifa –
  aj na **spotrebu domu do ďalšej NT** (mínus slnko, ktoré príde). Oplatí sa, keď cena NT so stratami + opotrebenie < cena VT.
- Energia, ktorá v okne ostane, sa **prenáša** do ďalšieho okna.
- V noci sa predá aj drahý slot, ak sa batéria potom **stihne dobiť** na ranný cieľ.
- Batéria **nikdy neklesne pod min SOC** – ani predajom, ani spotrebou domu (potom ide dom zo siete). Keď je batéria na minime a svieti slnko, predáva sa **len FVE**.
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

### Ovládacie karty

Tiež sa inštalujú s integráciou a **netreba ich nastavovať**:

- **Igy Battery Action Card** – čo batéria robí a prečo, min/max SOC, min. predajná cena (v *Pokročilých* nabíjací výkon a korekcia FVE).
- **Igy EV Action Card** – režim nabíjania auta, čas štartu, prúd, z čoho smie AI nabíjať a prepínač *Riadiť nabíjačku*.

## Inštalácia cez HACS

1. HACS → **⋮ → Vlastné repozitáre** (Custom repositories).
2. URL: `https://github.com/Igypop78/ai-energy`, kategória **Integration** → Pridať.
3. Nájdi **AI Energy** → Stiahnuť → **reštartuj Home Assistant**.
4. **Nastavenia → Zariadenia a služby → Pridať integráciu → AI Energy**.

## Nastavenie

Sprievodca ide krok po kroku a pri každom poli vysvetľuje, čo tam patrí. Kroky pre FVE a auto uvidíš len vtedy,
ak ich máš.

1. **Vitaj** – čo integrácia potrebuje a čo máš doma (FVE, nabíjačka auta).
2. **Spotové ceny** – senzor s cenami na dnes (povinný) a na zajtra. OKTE sa nájde automaticky.
3. **Nákup elektriny** – časy nízkej tarify a ceny v **€/kWh** vrátane distribúcie a DPH.
   Predvyplnené ZSE DD3: NT `23:45-05:45, 13:45-15:45`, NT 0,120 €/kWh, VT 0,210 €/kWh.
   Pri jednej tarife nechaj časy prázdne.
4. **Predaj elektriny** – *spotová cena mínus poplatok* (napr. 0,015 €/kWh), *pevná výkupná cena*
   (voliteľne s pásmom s inou cenou) alebo *nepredávam*.
5. **Batéria a spotreba domu** – SOC, kapacita, výkon nabíjania a predaja, spotreba domu v **kWh/deň**
   a voliteľne senzor spotreby (priemer z posledných 7 dní).
6. **Fotovoltika** – predpoveď Solcast a voliteľne okamžitý výkon FVE.
7. **Ovládanie meniča** – výber režimu (napr. `input_select.deye_operation_mode`), priradenie režimov,
   voliteľne nabíjací prúd zo siete a napätie batérie.
8. **Nabíjačka auta** – zapnutie nabíjania, prúd, fázy, stav auta. Pri výbere režimu (SmartEVSE) ďalší krok
   ponúkne jeho režimy na výber (Normal / Off).
9. **Istič a elektromer** – hlavný istič v A (napr. 25 pre 3×25 A), meranie odberu zo siete;
   v *Pokročilých* rezerva ističa a spoločný limit batérie a auta.
10. **Hotovo** – zhrnutie a čo ďalej.

Všetko sa dá neskôr zmeniť: **Nastavenia → Zariadenia a služby → AI Energy → Konfigurovať** – ponuka s rovnakými časťami.

## Plán vývoja

- [x] Záloha cien, aktuálna cena, nízka tarifa
- [x] Plánovač batérie (predaj v najdrahších slotoch, nabíjanie v NT, predpoveď FVE)
- [x] Karta s cenami a plánom (Igy Price Action Card) – inštaluje sa spolu s integráciou
- [x] Nabíjanie auta (NT, prebytky FVE, lacný spot, od času), limity ističa a kábla
- [x] Riadenie meniča cez výber režimu s mapovaním, ručný režim na čas, nabíjací prúd zo siete
- [ ] Blueprint pre Deye / Solarman (pre tých, čo nemajú vlastnú automatizáciu)
- [ ] Ďalšie meniče a tarify

## Vyskúšanie bez batérie (testovacia inštalácia)

Vytvor si pomocníka **Nastavenia → Zariadenia a služby → Pomocníci → Vytvoriť → Číslo**:
názov *Sim SOC*, 0–100, krok 1, jednotka %. V 3. kroku sprievodcu ho vyber ako **SOC batérie**.
Posúvaním hodnoty uvidíš, ako sa mení plán a odporúčaný režim.

## Licencia

MIT
