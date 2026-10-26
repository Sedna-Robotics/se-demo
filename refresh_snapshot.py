"""Rebuild snapshot.json (the offline fallback) from NOAA NEFSC ERDDAP FIShBOT.

Usage:  python3 refresh_snapshot.py            # writes snapshot.json next to this script
Needs only the Python standard library. Keep AREA and START in sync with index.html.
"""
import csv, io, json, datetime, pathlib, urllib.parse, urllib.request

ERDDAP = "https://comet.nefsc.noaa.gov/erddap/tabledap/ondeckdata_erddap_4319_ff7a_72eb.csv"
AREA = dict(latMin=40.3, latMax=45.2, lonMin=-74.0, lonMax=-65.5)
START = f"{datetime.date.today().year - 2}-01-01"


def query(variables, agg):
    parts = [variables,
             f"latitude>={AREA['latMin']}", f"latitude<={AREA['latMax']}",
             f"longitude>={AREA['lonMin']}", f"longitude<={AREA['lonMax']}",
             f"time>={START}", f'{agg}("time/1month,latitude,longitude")']
    url = ERDDAP + "?" + "&".join(urllib.parse.quote(p, safe=",=") for p in parts)
    with urllib.request.urlopen(url, timeout=120) as r:
        rows = list(csv.reader(io.TextIOWrapper(r, encoding="latin-1")))
    return rows[2:]  # skip header and units rows


def main():
    means = query("time,latitude,longitude,depth,temperature", "orderByMean")
    counts = {(t, f"{float(la):.4f}", f"{float(lo):.4f}"): int(float(n))
              for t, la, lo, n in query("time,latitude,longitude,temperature", "orderByCount")}
    obs = []
    for t, la, lo, z, temp in means:
        if not temp or temp == "NaN":
            continue
        la4, lo4 = f"{float(la):.4f}", f"{float(lo):.4f}"
        obs.append([int(t[:4]), int(t[5:7]), float(la4), float(lo4), round(float(temp), 2),
                    round(float(z)), counts.get((t, la4, lo4), 1)])
    out = {"fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
           "source": "NOAA NEFSC ERDDAP FIShBOT", "obs": obs}
    path = pathlib.Path(__file__).with_name("snapshot.json")
    path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {len(obs)} cell-months to {path}")


if __name__ == "__main__":
    main()
