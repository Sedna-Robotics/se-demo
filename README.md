# Species Temperature Band Map

A phone-first web app for showing fishermen where the water is in their target
species' preferred temperature band, on 1 nm squares across New England.

- **Setup screen:** who it is for, a species, and an area of interest (presets,
  or draw a rectangle or polygon). A QR code links phones to the app.
- **Results screen:** the area at the latest month with data, the share of
  squares in band, a month strip to step back through time, and a zoomable map.
  "Change" goes back to set up the next person. Recent setups stay on the
  device for quick switching, and the URL opens straight to the same view.

Live at https://sedna-robotics.github.io/se-demo/

## Species

| Kind | What is compared | Species |
|---|---|---|
| Bottom | Monthly mean bottom temperature per square | Lobster, black sea bass, sea scallop, winter skate, spiny dogfish, monkfish, Atlantic cod, summer flounder |
| Midwater | Monthly mean water-column profile per square | Longfin squid, shortfin squid (Illex), Atlantic mackerel, Atlantic herring, butterfish |

For midwater species a square is green when any part of its profile is in the
band. Its number is the middle of the thickest in-band layer, in fathoms: the
suggested target depth for nets, jigs or other gear. Tap a square for the in-band layer's top and bottom and the
surface and deepest temperatures. Bands and sources are in the
`SP` list in `index.html` and under "Species bands and sources" in the app.

## Data

All sources are temperature sensors on commercial fishing gear or fishing-vessel
research fleets. `refresh_data.py` asks each ERDDAP server to average its data
into 1 nm squares (1 minute of latitude by 0.0225° of longitude, about 1 nm at
42° N) and calendar months, then combines the sources. Bottom squares cover the
last 3 years; water-column profiles cover the last 12 months in 5 m layers.

| Source | Server | Used for |
|---|---|---|
| eMOLT (`eMOLT_RT`), fishing segments | erddap.emolt.net | Bottom |
| eMOLT, gear going down and coming up | erddap.emolt.net | Profiles |
| Maine Coast Fishermen's Association (`MCFA_RT`) | erddap.emolt.net | Bottom and profiles |
| CFRF fixed gear (`fixed_gear_oceanography`) | erddap.ondeckdata.com | Bottom |
| CFRF trap-haul casts (`mobile_gear_oceanography`) | erddap.ondeckdata.com | Profiles |
| CFRF/WHOI Shelf Research Fleet CTD, 1 m binned | erddap.ondeckdata.com | Profiles |
| South Fork Wind survey CTD, 1 m binned | erddap.ondeckdata.com | Profiles |
| South Fork Wind acoustic receiver thermistors | erddap.ondeckdata.com | Bottom |
| Demersal gliders, aggregated bottom data | erddap.ondeckdata.com | Bottom |

Left out on purpose:

- **Full Resolution CTD** datasets: the same casts as the 1 m binned versions.
- **QAQC Flagged Oceanographic Data**: the raw, unedited CFRF fixed and mobile
  gear records with QA flags attached, including values that failed. The
  `fixed_gear_oceanography` and `mobile_gear_oceanography` datasets are the
  same records with only passing values kept, so using the flagged one too
  would double count.
- **`emolt_data`** on OnDeck: redirects to eMOLT's own server, already used.
- **FIShBOT** (`fishbot_realtime`, `fishbot_archive`): a 7 km product built from
  these same sources, so it would double count.

Each square records which sources fed it; tapping a square lists them.

### Daily refresh

`.github/workflows/refresh.yml` runs `refresh_data.py` every day at 09:17 UTC
and commits `snapshot.json` and `profiles.json` when they change, which
redeploys GitHub Pages. Run it by hand from the Actions tab ("Refresh data",
then "Run workflow"), or locally:

    python3 refresh_data.py      # about 3 to 4 minutes, standard library only

The dot at the top of the app shows when the files were last rebuilt. Depth
contours are GEBCO 2024.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole app. Loads d3 7.8.5 and qrcode-generator 1.4.4 from cdnjs. |
| `snapshot.json` | 1 nm bottom temperatures, with a source mask per square. |
| `profiles.json` | 1 nm water-column profiles in 5 m layers, with a source mask. |
| `bathy.json`, `bathy-ne.jpg`, `bathy-cape.jpg` | Seafloor relief, coastline and fathom contours. |
| `refresh_data.py` | Rebuilds both data files from ERDDAP. |
| `.github/workflows/refresh.yml` | Runs the rebuild daily. |
| `.nojekyll` | Tells GitHub Pages to serve the files as they are. |

## Changing things

- Area: `AREA` in `refresh_data.py`. The relief images
  cover 40.0 to 45.4 N, 74.3 to 65.2 W.
- Preset areas: `PRESETS` (rectangles as corner lists, longitude first).
- QR target: `APP_URL_DEFAULT`; on a hosted page the QR uses the page's own URL.
