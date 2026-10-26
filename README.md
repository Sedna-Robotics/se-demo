# Species Temperature Band Map

A phone-first web app for showing fishermen where the water is in their target
species' preferred temperature band, on NOAA's FIShBOT 7 km grid across New England.

- **Setup screen:** a species and an area of interest (presets, or draw a
  rectangle or polygon). A QR code links phones to the app.
- **Results screen:** the area at the latest month with data, the share of
  squares in band, a month strip to step back through time, and a zoomable map.
  "Change" goes back to pick another species or area, and the URL opens
  straight to the same view. The DOPPIO model switch sits with the stats, and
  a fm · °F / m · °C selector at the top is remembered on each device.

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

Sources are temperature sensors on commercial fishing gear, fishing-vessel
research fleets, Massachusetts DMF monitoring, and NOAA/IOOS surveys.
`refresh_data.py` asks each ERDDAP server to average its data
into fine 1 nm bins by calendar month, then snaps every bin onto the FIShBOT
grid (FIShBOT's own `botgrid`: 7000 m cells in UTM zone 19N, stored here as
`fishbot_grid.json`) and combines the sources. The DMF ArcGIS layers are point data, so each reading is
placed directly in the FIShBOT cell that contains it. Squares line up exactly with
FIShBOT's, so values can be compared cell for cell. Bottom squares cover the
last 3 years, and so do water-column profiles, in 5 m layers.

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
| Mass. DMF Cape Cod Bay DO study fleet loggers (`DMF_Avg_DO_PublicView` and yearly archives) | services1.arcgis.com | Bottom |
| Mass. DMF bottom temperature stations (`MA_Ocean_Bottom_Temperature_Sensor_Data`) | services1.arcgis.com | Bottom |
| NOAA NEFSC ECOMON and survey CTD (`ocdbs_v_erddap1`, bottles excluded) | comet.nefsc.noaa.gov | Profiles |
| IOOS Glider DAC deployments in the area, found at run time (delayed mode preferred) | gliders.ioos.us | Profiles |

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
- **DMF DO 2025 archive**: the ArcGIS layer needs a sign-in token, so 2025
  logger data is missing until DMF makes it public.
- **DMF stations Endicott and Sculpin**: no location in DMF's station layer.
- **`eMOLT_RT_LOWELL`**: marked "DO test, DATA NOT FOR USE".
- **NERACOOS buoys**: surface and fixed-depth moorings, few bottom or profile
  points per FIShBOT cell; could be added later as point sources.
- **OOI Pioneer array**: mostly south of the area's 40.3 N edge.
- **Oleander XBT line**: crosses the shelf south of the area.
- **NEFSC Study Fleet**: not published on a public server.

Each square records which sources fed it; tapping a square lists them.

### DOPPIO model layer (optional)

The DOPPIO model switch on the results screen fills squares with no
observations from DOPPIO, and adds the model's in-band squares to the month bar
graph as hatched segments on top of the observed counts. The model comes from DOPPIO, Rutgers' 7 km data-assimilating ROMS model
(`roms/doppio/2017_da/avg/Averages_Best_Excluding_Day1` on
tds.marine.rutgers.edu). `refresh_data.py` samples the daily averages weekly
for bottom temperature (last 3 years) and every 10 days for profiles (last 3 years,
5 m layers to 150 m), places each model point in its FIShBOT cell
(squares without one take the nearest model point within 7 km), and writes
`doppio/doppio.json` plus one `doppio/prof-YYYY-MM.json` per month. The app
loads them only when the switch is on. Model squares are hatched and never replace
observations. Model bottom temperature differs from the observed squares by
about 0.9 °C on average, with a bias of about -0.15 °C.

**Certificate.** The Rutgers server's certificate chains to "emSign Root CA -
G1", which is in Chrome's and Microsoft's root stores but not in the Python or
Ubuntu bundles. `certs/emsign-root-ca-g1.pem` holds that root. The script
checks its SHA-256 fingerprint
(`40F6AF03...C8D00367`, matching emSign's repository and Chrome's root store)
and trusts it for the DOPPIO requests only. Every other request uses the
standard trust store, and TLS verification is never turned off.

### Daily refresh

`.github/workflows/refresh.yml` runs `refresh_data.py` every day at 09:17 UTC
and commits `snapshot.json`, `profiles.json`, `grid.json` and `doppio/` when they change, which
redeploys GitHub Pages. Run it by hand from the Actions tab ("Refresh data",
then "Run workflow"), or locally:

    python3 refresh_data.py      # about 30 minutes, standard library only

The dot at the top of the app shows when the files were last rebuilt. Depth
contours are GEBCO 2024.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole app. Loads d3 7.8.5 and qrcode-generator 1.4.4 from cdnjs. |
| `grid.json` | Corners of every FIShBOT cell that has data, for drawing. |
| `fishbot_grid.json` | The full FIShBOT grid (cell id, row, column, centroid, corners). |
| `snapshot.json` | Bottom temperatures per FIShBOT cell, with a source mask per square. |
| `doppio/` | DOPPIO model layer: cell index with monthly bottom temperatures, plus monthly profile files. |
| `certs/emsign-root-ca-g1.pem` | Pinned root certificate for the Rutgers DOPPIO server. |
| `profiles.json` | Water-column profiles per FIShBOT cell in 5 m layers, with a source mask. |
| `bathy.json`, `bathy-ne.jpg`, `bathy-cape.jpg` | Seafloor relief, coastline and fathom contours. |
| `refresh_data.py` | Rebuilds the data files from ERDDAP and the DMF ArcGIS layers. |
| `.github/workflows/refresh.yml` | Runs the rebuild daily. |
| `.nojekyll` | Tells GitHub Pages to serve the files as they are. |

## Changing things

- Area: `AREA` in `refresh_data.py`. The relief images
  cover 40.0 to 45.4 N, 74.3 to 65.2 W.
- Preset areas: `PRESETS` (rectangles as corner lists, longitude first).
- QR target: `APP_URL_DEFAULT`; on a hosted page the QR uses the page's own URL.
