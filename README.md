# IMS Weather (Motinium)

[![GitHub Release][releases-shield]][releases]
[![Tests][tests-shield]][tests]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

![Project Maintenance][maintenance-shield]

Home Assistant integration for the **Israel Meteorological Service** — current
conditions, a seven-day forecast, official weather warnings including marine
ones, and a daily digest of the hours worth knowing about.

A personal fork, running under its own domain (`ims_motinium`) so it installs
independently of any other IMS integration. English only.

---

## What this fork adds

**The reload bug is fixed.** In the original, reloading the config entry left a
shut-down coordinator in the cache and the next setup reused it, so updates
stopped until Home Assistant was fully restarted.

**Marine warnings.** IMS files them against the sea regions, never against the
land region a coastal city sits in, so they were invisible: five active sea
alerts while the location's own warnings sensor showed one.

**Structured warning data.** Severity, type, audience groups, covered regions
and a stable id, instead of only free text a card had to parse.

**A daily digest.** One line summarising the notable hours left today, with
thresholds you set in the UI.

**Model freshness.** IMS precomputes ten-minute slots hours ahead, so a stalled
model keeps serving advancing timestamps. `ims_last_modified` shows when the
run was actually computed.

**No dependency on GitHub at startup.** The patched `weatheril` library ships
inside the integration; Home Assistant re-resolves URL requirements on every
start, and an outage there used to stop the integration from loading.

The library also carries fixes of its own: a cache that never expired under
frequent polling, HTTP timeouts, a removed global IPv6 monkeypatch that
disabled IPv6 for the whole Home Assistant process, thread-safe lookup caches
and several crashes on partial IMS responses.

---

## Installation

1. HACS → three-dot menu → **Custom repositories**
2. Add `https://github.com/Motinium/ims-weather-motinium`, category
   **Integration**
3. Download it, then **restart Home Assistant**
4. **Settings → Devices & Services → Add Integration** → *IMS Weather
   (Motinium)*
5. Pick your city (see the table at the end) and confirm

> If the original `GuyKh/ims-custom-component` is installed, remove its config
> entry first. The domains differ, so both can be installed, but their entity
> ids collide.

### Configuration

**Settings → Devices & Services → IMS Weather (Motinium) → Configure** offers
two pages:

- **Main settings** — city, update interval, which platforms to create, and
  **Monitored conditions**: the list of sensors to create.
- **Daily digest thresholds** — see below.

> Sensors are opt-in and the choice is stored in the entry. A sensor added by a
> later version does **not** appear until you tick it here.

---

## Entities

Current conditions: temperature, feels like, humidity, wind speed and
direction, gusts, precipitation and its probability, dew point, PM10, UV index
and level, max UV, city.

Forecast: `ims_forecast_today` and `ims_forecast_day1` … `day7`. Each carries
per-hour attributes keyed by time (`"14:00"`). Today also carries the full
hourly set — humidity, wind, gusts, wind chill, heat stress, UV, PM10, wave
height — with the units declared once in `hourly_units`:

```jinja
{{ state_attr('sensor.ims_forecast_today', '14:00').humidity }}
```

Diagnostics: `ims_forecast_time` (which slot a value belongs to) and
`ims_last_modified` (when IMS last recomputed the run). The gap between them is
the real age of the data:

```jinja
{{ (now() - states('sensor.ims_last_modified') | as_datetime).total_seconds() / 3600 }}
```

Binary: `ims_is_raining`, `ims_is_active_weather_warning`.

### Warnings

`ims_weather_warnings` and `ims_sea_warnings` hold the number of active alerts
for your region and for the sea regions. Both expose a `warnings_data`
attribute, a list of:

| Field | |
|---|---|
| `severity` | `Yellow Warning`, `Orange Early Warning`, `Red Warning`, … |
| `severity_color` | the hex colour IMS itself uses for that level |
| `type` | `High Sea Swimming Danger`, `Heat Stress`, `Extreme Temperature`, … |
| `groups` | audience: `General Public`, `Seamanship`, `Aviation`, `Agriculture`, `Roads` |
| `region` / `regions` | your region, and every region the alert covers |
| `id` | stable alert id — the same alert is filed against several regions |
| `sent` | when IMS issued it |
| `valid_from` / `valid_to` | ISO timestamps |
| `text` | the full text |

The older `warnings` attribute (a list of strings) is still there.

### Daily digest

`ims_daily_digest` counts the notable hours left in today's forecast — nothing
on an ordinary day. `items` holds one entry per finding with `metric`, `label`,
`peak`, `unit` and the hour window; `summary` is a ready-made English line.

Thresholds and which rules run are set in **Configure → Daily digest
thresholds**. Defaults are deliberately above ordinary conditions, calibrated
against a normal week in Akko so a quiet day stays empty:

| Rule | Default |
|---|---|
| High temperature / Cold | above 35 °C / below 8 °C |
| Heat stress level | 4 |
| UV index | 8 |
| Wind gusts / Wind speed | 50 / 35 km/h |
| Dust PM10 | 80 µg/m³ |
| Rain chance / Rainfall | 40 % / 1 mm |

Humidity is deliberately not a rule: IMS already folds it into the heat stress
level.

---

## Dashboard cards

Both cards read the structured attributes, so they need no text parsing. Labels
are plain strings — translate them to taste.

### Warnings

Local alerts meant for the public, plus marine alerts, newest severity first,
de-duplicated by id. The card hides itself when there is nothing to show.

```yaml
type: conditional
conditions:
  - condition: or
    conditions:
      - condition: numeric_state
        entity: sensor.ims_weather_warnings
        above: 0
      - condition: numeric_state
        entity: sensor.ims_sea_warnings
        above: 0
card:
  type: markdown
  content: >
    {%- set land = state_attr('sensor.ims_weather_warnings','warnings_data') or [] -%}
    {%- set sea  = state_attr('sensor.ims_sea_warnings','warnings_data') or [] -%}
    {%- set ns = namespace(items=[], seen=[], ranked=[], out=[]) -%}

    {#- local alerts, public ones only -#}
    {%- for a in land -%}
      {%- if 'General Public' in (a.groups or []) and a.id not in ns.seen -%}
        {%- set ns.seen = ns.seen + [a.id] -%}
        {%- set ns.items = ns.items + [{'a': a, 'src': 'Local'}] -%}
      {%- endif -%}
    {%- endfor -%}

    {#- marine alerts: the real sea regions, not the inland waters IMS also
        flags as sea (Sea of Galilee, Gulf of Eilat) -#}
    {%- for a in sea -%}
      {%- set is_sea = (a.regions or []) | select('search', '^Sea \\(') | list | length > 0 -%}
      {%- if is_sea and a.id not in ns.seen -%}
        {%- set ns.seen = ns.seen + [a.id] -%}
        {%- set ns.items = ns.items + [{'a': a, 'src': 'Sea'}] -%}
      {%- endif -%}
    {%- endfor -%}

    {#- most severe first -#}
    {%- for it in ns.items -%}
      {%- set s = (it.a.severity or '') | lower -%}
      {%- set r = 0 if 'red' in s else 1 if 'orange' in s else 2 if 'yellow' in s else 3 -%}
      {%- set ns.ranked = ns.ranked + [{'r': r, 'a': it.a, 'src': it.src}] -%}
    {%- endfor -%}

    {%- for it in ns.ranked | sort(attribute='r') -%}
      {%- set a = it.a -%}
      {%- set s = (a.severity or '') | lower -%}
      {%- set typ = (a.type or '') | lower -%}

      {%- if 'red' in s -%}{%- set dot = '🔴' -%}
      {%- elif 'orange' in s -%}{%- set dot = '🟠' -%}
      {%- elif 'yellow' in s -%}{%- set dot = '🟡' -%}
      {%- elif 'green' in s -%}{%- set dot = '🟢' -%}
      {%- else -%}{%- set dot = '⚪' -%}{%- endif -%}

      {%- if 'swim' in typ -%}{%- set icon = '🏊' -%}
      {%- elif 'sea' in typ or 'wave' in typ -%}{%- set icon = '🌊' -%}
      {%- elif 'heat' in typ or 'fire' in typ -%}{%- set icon = '🔥' -%}
      {%- elif 'flood' in typ or 'rain' in typ or 'thunder' in typ -%}{%- set icon = '🌧️' -%}
      {%- elif 'wind' in typ -%}{%- set icon = '💨' -%}
      {%- elif 'visib' in typ or 'fog' in typ -%}{%- set icon = '🌫️' -%}
      {%- elif 'snow' in typ or 'frost' in typ -%}{%- set icon = '❄️' -%}
      {%- else -%}{%- set icon = '📢' -%}{%- endif -%}

      {%- set vf = as_datetime(a.valid_from) -%}
      {%- set vt = as_datetime(a.valid_to) -%}
      {%- set tline = (vf.strftime('%d/%m %H:%M') ~ ' → ' ~ vt.strftime('%d/%m %H:%M')) if (vf and vt) else '' -%}

      {%- set block = dot ~ ' **' ~ icon ~ ' ' ~ (a.severity or '') ~ ' — ' ~ (a.type or '') ~ '**  \n'
            ~ '<sub>' ~ it.src ~ '</sub>'
            ~ ('\n\n🕒 ' ~ tline if tline else '')
            ~ ('\n\n' ~ a.text if a.text else '') -%}
      {%- set ns.out = ns.out + [block] -%}
    {%- endfor -%}

    {%- if ns.out -%}{{ ns.out | join('\n\n---\n\n') }}{%- else -%}✅ No active warnings{%- endif -%}
```

To include marine alerts aimed at sailors rather than swimmers, drop the
`General Public` check; to hide them, add the same check to the sea loop.

> Home Assistant's markdown card strips inline styles, so `severity_color`
> cannot be applied as `<span style="color:…">`. Hence the emoji circles. With
> [card-mod](https://github.com/thomasloven/lovelace-card-mod) the real IMS
> colour can be used.

### Daily digest

```yaml
type: conditional
conditions:
  - condition: numeric_state
    entity: sensor.ims_daily_digest
    above: 0
card:
  type: markdown
  content: >
    {%- set items = state_attr('sensor.ims_daily_digest','items') or [] -%}
    {%- set icons = {
        'temperature': '🌡️', 'heat_stress_level': '🥵', 'uv_index': '☀️',
        'gust_speed': '💨', 'wind_speed': '💨', 'pm10': '🌪️',
        'rain_chance': '🌧️', 'rain': '🌧️' } -%}
    {%- set ns = namespace(out=[]) -%}
    {%- for i in items -%}
      {%- set win = i['from'] if i['from'] == i['to'] else i['from'] ~ '–' ~ i['to'] -%}
      {%- set ns.out = ns.out + [
          (icons.get(i.metric, '📌')) ~ ' **' ~ i.label ~ '** — '
          ~ i.peak ~ ' ' ~ (i.unit or '') ~ '  \n<sub>🕒 ' ~ win ~ '</sub>' ] -%}
    {%- endfor -%}
    ### 📋 Worth knowing today
    {{ ns.out | join('\n\n') }}
```

---

## Notes

**Recorder.** Forecast attributes are rewritten on every poll and their history
is of little use. Excluding them keeps the database small:

```yaml
recorder:
  exclude:
    entity_globs:
      - sensor.ims_forecast_day*
    entities:
      - sensor.ims_forecast_today
```

**Radar and satellite imagery is not exposed.** IMS answers the per-frame radar
PNGs with a 2-byte placeholder instead of an image, so an animation cannot be
built. The satellite JPEGs do work, but they cover the whole Middle East at one
frame per hour, which is too coarse to be useful locally.

**Data is a model, not a measurement.** The "current" values come from IMS's
nowcast: values are precomputed for ten-minute slots hours in advance, which is
why neighbouring readings can differ by more than the weather does.
`ims_last_modified` shows when the run behind them was computed.

---

## Development

```bash
pip install pytest pytz requests
pytest tests/test_library.py          # parses captured IMS responses, no network
pytest tests/test_digest.py           # digest rules, needs Home Assistant
```

Both run on every push via GitHub Actions. The `weatheril` library lives in
`custom_components/ims_motinium/weatheril/` and is maintained here;
[Motinium/py-weatheril-motinium](https://github.com/Motinium/py-weatheril-motinium)
is archived.

---

## City ids

| Id | Location |
| ------------ | ----------- |
| 1| Jerusalem|
| 2| Tel Aviv - Yafo|
| 3| Haifa|
| 4| Rishon le Zion|
| 5| Petah Tiqva|
| 6| Ashdod|
| 7| Netania|
| 8| Beer Sheva|
| 9| Bnei Brak|
| 10| Holon|
| 11| Ramat Gan|
| 12| Asheqelon|
| 13| Rehovot|
| 14| Bat Yam|
| 15| Bet Shemesh|
| 16| Kfar Sava|
| 17| Herzliya|
| 18| Hadera|
| 19| Modiin|
| 20| Ramla|
| 21| Raanana|
| 22| Modiin Illit|
| 23| Rahat|
| 24| Hod Hasharon|
| 25| Givatayim|
| 26| Kiryat Ata|
| 27| Nahariya|
| 28| Beitar Illit|
| 29| Um al-Fahm|
| 30| Kiryat Gat|
| 31| Eilat|
| 32| Rosh Haayin|
| 33| Afula|
| 34| Nes-Ziona|
| 35| Akko|
| 36| Elad|
| 37| Ramat Hasharon|
| 38| Karmiel|
| 39| Yavneh|
| 40| Tiberias|
| 41| Tayibe|
| 42| Kiryat Motzkin|
| 43| Shfaram|
| 44| Nof Hagalil|
| 45| Kiryat Yam|
| 46| Kiryat Bialik|
| 47| Kiryat Ono|
| 48| Maale Adumim|
| 49| Or Yehuda|
| 50| Zefat|
| 51| Netivot|
| 52| Dimona|
| 53| Tamra |
| 54| Sakhnin|
| 55| Yehud|
| 56| Baka al-Gharbiya|
| 57| Ofakim|
| 58| Givat Shmuel|
| 59| Tira|
| 60| Arad|
| 61| Migdal Haemek|
| 62| Sderot|
| 63| Araba|
| 64| Nesher|
| 65| Kiryat Shmona|
| 66| Yokneam Illit|
| 67| Kafr Qassem|
| 68| Kfar Yona|
| 69| Qalansawa|
| 70| Kiryat Malachi|
| 71| Maalot-Tarshiha|
| 72| Tirat Carmel|
| 73| Ariel|
| 74| Or Akiva|
| 75| Bet Shean|
| 76| Mizpe Ramon|
| 77| Lod|
| 78| Nazareth|
| 79| Qazrin|
| 80| En Gedi|
| 200| Nimrod Fortress|
| 201| Banias|
| 202| Tel Dan|
| 203| Snir Stream|
| 204| Horshat Tal |
| 205| Ayun Stream|
| 206| Hula|
| 207| Tel Hazor|
| 208| Akhziv|
| 209| Yehiam Fortress|
| 210| Baram|
| 211| Amud Stream|
| 212| Korazim|
| 213| Kfar Nahum|
| 214| Majrase |
| 215| Meshushim Stream|
| 216| Yehudiya |
| 217| Gamla|
| 218| Kursi |
| 219| Hamat Tiberias|
| 220| Arbel|
| 221| En Afek|
| 222| Tzipori|
| 223| Hai-Bar Carmel|
| 224| Mount Carmel|
| 225| Bet Shearim|
| 226| Mishmar HaCarmel |
| 227| Nahal Me‘arot|
| 228| Dor-HaBonim|
| 229| Tel Megiddo|
| 230| Kokhav HaYarden|
| 231| Maayan Harod|
| 232| Bet Alpha|
| 233| Gan HaShlosha|
| 235| Taninim Stream|
| 236| Caesarea|
| 237| Tel Dor|
| 238| Mikhmoret Sea Turtle|
| 239| Beit Yanai|
| 240| Apollonia|
| 241| Mekorot HaYarkon|
| 242| Palmahim|
| 243| Castel|
| 244| En Hemed|
| 245| City of David|
| 246| Me‘arat Soreq|
| 248| Bet Guvrin|
| 249| Sha’ar HaGai|
| 250| Migdal Tsedek|
| 251| Haniya Spring|
| 252| Sebastia|
| 253| Mount Gerizim|
| 254| Nebi Samuel|
| 255| En Prat|
| 256| En Mabo‘a|
| 257| Qasr al-Yahud|
| 258| Good Samaritan|
| 259| Euthymius Monastery|
| 261| Qumran|
| 262| Enot Tsukim|
| 263| Herodium|
| 264| Tel Hebron|
| 267| Masada |
| 268| Tel Arad|
| 269| Tel Beer Sheva|
| 270| Eshkol|
| 271| Mamshit|
| 272| Shivta|
| 273| Ben-Gurion’s Tomb|
| 274| En Avdat|
| 275| Avdat|
| 277| Hay-Bar Yotvata|
| 278| Coral Beach|

---

Based on [GuyKh/ims-custom-component](https://github.com/GuyKh/ims-custom-component)
and [t0mer/py-weatheril](https://github.com/t0mer/py-weatheril).

[commits-shield]: https://img.shields.io/github/commit-activity/y/Motinium/ims-weather-motinium.svg?style=for-the-badge
[commits]: https://github.com/Motinium/ims-weather-motinium/commits/main
[license-shield]: https://img.shields.io/github/license/Motinium/ims-weather-motinium.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40Motinium-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/Motinium/ims-weather-motinium.svg?style=for-the-badge
[releases]: https://github.com/Motinium/ims-weather-motinium/releases
[tests-shield]: https://img.shields.io/github/actions/workflow/status/Motinium/ims-weather-motinium/tests.yml?branch=main&style=for-the-badge&label=tests
[tests]: https://github.com/Motinium/ims-weather-motinium/actions/workflows/tests.yml
