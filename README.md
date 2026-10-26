# Species Temperature Band Map

A phone-first web app for showing fishermen where the water is in their target
species' preferred temperature band, on 1 nm squares across New England.

- **Setup screen:** who it is for, a species, and an area of interest (presets,
  or draw a rectangle or polygon). A QR code links phones to the app.
- **Results screen:** the area at the latest month with data, the share of
  squares in band, a month strip to step back through time, and a zoomable map.
  "Change" goes back to edit; "Next person" starts fresh. Recent setups stay on
  the device for quick switching, and the URL opens straight to the same view.

Live at https://sedna-robotics.github.io/se-demo/

## Species

| Kind | What is compared | Species |
|---|---|---|
| Bottom | Monthly mean bottom temperature per square | Lobster, black sea bass, sea scallop, winter skate, spiny dogfish, monkfish, Atlantic cod, summer flounder |
| Midwater | Monthly mean water-column profile per square | Longfin squid, shortfin squid (Illex), Atlantic mackerel, Atlantic herring, butterfish |

For midwater species a square is green when any part of its profile is in the
band. Its number is the middle of the thickest in-band layer, in fathoms: the
suggested net depth. Tap a square for the in-band layer's top and bottom and the
surface and deepest temperatures. Bands and sources are in the
`SP` list in `index.html` and under "Species bands and sources" in the app.

## Data

Readings come from temperature sensors on commercial fishing gear, served by
ERDDAP at erddap.emolt.net: `eMOLT_RT` (eMOLT) and `MCFA_RT` (Maine Coast
Fishermen's Association). Both are quality-controlled by the providers.

- **Bottom:** readings while gear is fishing on or near the bottom
  (`segment_type=3`), averaged by ERDDAP into 1 nm squares (1 minute of latitude
  by 0.0225° of longitude, about 1 nm at 42° N) and calendar months.
- **Midwater:** profiling readings while gear is set and hauled
  (`segment_type` 1 and 2), averaged by square, month and 5 m layer, for the
  last 12 months.

The page opens with the saved files (`snapshot.json`, `profiles.json`) so it
draws instantly, then asks ERDDAP for the latest two months and swaps them in.
The dot at the top of each screen says "Live" or "Saved".

ERDDAP does not send CORS headers, so the page uses ERDDAP's JSONP option
(`&.jsonp=callback`), which loads the response as a script from
erddap.emolt.net. If your host sets a Content-Security-Policy, allow
`https://erddap.emolt.net` in `script-src`. Depth contours are GEBCO 2024.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole app. Loads d3 7.8.5 and qrcode-generator 1.4.4 from cdnjs. |
| `snapshot.json` | Saved 1 nm bottom temperatures (about 3 years). |
| `profiles.json` | Saved 1 nm water-column profiles (last 12 months). |
| `bathy.json`, `bathy-ne.jpg`, `bathy-cape.jpg` | Seafloor relief, coastline and fathom contours. |
| `refresh_snapshot.py`, `refresh_profiles.py` | Rebuild the saved files from ERDDAP (standard library only). |
| `.nojekyll` | Tells GitHub Pages to serve the files as they are. |

## Refreshing the saved files

    python3 refresh_snapshot.py     # about 2 minutes
    python3 refresh_profiles.py     # about 2 minutes

Run them now and then (or from a scheduled GitHub Action) so the first paint
is recent. The live update does not depend on them.

## Changing things

- Area: `AREA` in `index.html` and in both refresh scripts. The relief images
  cover 40.0 to 45.4 N, 74.3 to 65.2 W.
- Preset areas: `PRESETS` (rectangles as corner lists, longitude first).
- QR target: `APP_URL_DEFAULT`; on a hosted page the QR uses the page's own URL.
