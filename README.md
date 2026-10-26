# Species Temperature Band Map

A static web app that shows monthly bottom temperatures from NOAA's FIShBOT grid
across New England, colored against the preferred temperature band of eight
species landed in the region. It opens zoomed on the Outer Cape and can zoom out
to all of New England.

## Files

| File | What it is |
|---|---|
| `index.html` | The whole app (HTML, CSS, JS). Loads d3 7.8.5 from cdnjs. |
| `bathy.json` | Fathom contours (10, 20, 30, 50, 100, 200 fm) and coastline, from GEBCO 2024. |
| `bathy-ne.jpg` | Shaded seafloor relief for New England. |
| `bathy-cape.jpg` | Higher-resolution relief for the Outer Cape, drawn over the regional image. |
| `snapshot.json` | Saved copy of the data, used only if the live pull fails. |
| `refresh_snapshot.py` | Rebuilds `snapshot.json` from ERDDAP (standard library only). |

## Hosting

Upload the folder to any static host (GitHub Pages, Netlify, Cloudflare Pages,
S3, or your own web server). No server code is needed. Serve it over http(s);
opening `index.html` straight from disk will not load the JSON files.

## How the live data works

On each page load the app asks NOAA NEFSC ERDDAP for monthly means per FIShBOT
grid square (bounds 40.3 to 45.2 N, 74.0 to 65.5 W, from January 1 two years
before the current year), plus a count of sampled days per square. ERDDAP does
the averaging server side, so the response stays small (about 10,000 rows).

ERDDAP does not send CORS headers, so a normal `fetch()` from another site is
blocked by the browser. The app uses ERDDAP's built-in JSONP option
(`&.jsonp=callback`) instead, which loads the response as a script. If that
fails or takes longer than 30 seconds, the app falls back to `snapshot.json`.
The pill under the title says which one you are seeing.

JSONP means the browser runs a script served by comet.nefsc.noaa.gov. If your
host sets a Content-Security-Policy, add `https://comet.nefsc.noaa.gov` to
`script-src`. If you would rather not run remote script, put a small proxy in
front of ERDDAP that adds an `Access-Control-Allow-Origin` header and switch
`loadLive()` to `fetch()`.

## Changing the area, years or species

- Area and time window: `AREA` and `START` near the top of the script in
  `index.html` (and the same values in `refresh_snapshot.py`).
- Starting view: `HOME_VIEW` (two corners, longitude then latitude).
- Species bands: the `SP` list. `lo` and `hi` are in degrees C; the page
  converts to Fahrenheit. Sources for each band are summarized in its `note`.
- The relief images and contours cover 40.0 to 45.4 N, 74.3 to 65.2 W. Expanding
  the area beyond that needs new bathymetry files.

## Refreshing the fallback snapshot

    python3 refresh_snapshot.py

Run it on a schedule (cron, a GitHub Action) if you want the fallback to stay
recent. The live pull does not depend on it.

## Data credits

- Bottom temperature: FIShBOT (Fishing Industry Shared Bottom Oceanographic
  Timeseries), NOAA NEFSC ERDDAP, built from eMOLT, CFRF, Study Fleet, ECOMON
  and partner data.
- Bathymetry: GEBCO 2024 Grid.
