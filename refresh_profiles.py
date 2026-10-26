"""Rebuild profiles.json: water-column temperature by 1 nm square, month and 5 m layer, for midwater species.

Uses eMOLT and MCFA profiling readings (segment_type 1 and 2: gear going down and coming up), binned server
side by ERDDAP to 1 nm squares, calendar months and 5 m depth layers. Covers the last 12 months.
Usage:  python3 refresh_profiles.py     (standard library only)
"""
import csv, io, json, datetime, pathlib, urllib.parse, urllib.request, concurrent.futures as cf

SOURCES = ["https://erddap.emolt.net/erddap/tabledap/eMOLT_RT", "https://erddap.emolt.net/erddap/tabledap/MCFA_RT"]
AREA = dict(latMin=40.3, latMax=45.2, lonMin=-74.0, lonMax=-65.5)
DLAT, DLON, DZ = 1 / 60, 0.0225, 5
MONTHS_BACK = 12


def windows():
    t = datetime.date.today().replace(day=1)
    y, m = t.year, t.month - (MONTHS_BACK - 1)
    while m <= 0: y, m = y - 1, m + 12
    while (y, m) <= (t.year, t.month):
        y2, m2 = (y, m + 2) if m + 2 <= 12 else (y + 1, m + 2 - 12)
        if (y2, m2) > (t.year, t.month): y2, m2 = t.year, t.month
        end = (datetime.date(y2 + (m2 == 12), (m2 % 12) + 1, 1) - datetime.timedelta(days=1))
        yield f"{y}-{m:02d}-01", end.isoformat() + "T23:59:59Z"
        y, m = (y2, m2 + 1) if m2 < 12 else (y2 + 1, 1)


def query(base, t0, t1):
    parts = ["time,latitude,longitude,depth,temperature",
             f"latitude>={AREA['latMin']}", f"latitude<={AREA['latMax']}",
             f"longitude>={AREA['lonMin']}", f"longitude<={AREA['lonMax']}",
             f"time>={t0}", f"time<={t1}", "segment_type<=2",
             f'orderByMean("time/1month,latitude/{DLAT:.6f},longitude/{DLON},depth/{DZ}")']
    url = base + ".csv?" + "&".join(urllib.parse.quote(p, safe=",=/") for p in parts)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "species-temperature-band-map/1.0"})
            with urllib.request.urlopen(req, timeout=600) as r:
                return list(csv.reader(io.TextIOWrapper(r, encoding="latin-1")))[2:]
        except urllib.error.HTTPError as e:
            if e.code == 404: return []
            if attempt == 2: raise
        except Exception:
            if attempt == 2: raise


def main():
    jobs = [(s, t0, t1) for s in SOURCES for t0, t1 in windows()]
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        res = list(ex.map(lambda j: query(*j), jobs))
    acc = {}
    for rows in res:
        for t, la, lo, z, temp in rows:
            if not temp or temp == "NaN": continue
            key = (t[:7], int(float(la)), int(float(lo)))
            layer = int(float(z))
            a = acc.setdefault(key, {}).setdefault(layer, [0.0, 0])
            a[0] += float(temp); a[1] += 1
    out = []
    for (ym, i, j), layers in sorted(acc.items()):
        top = max(layers)
        temps = [round(layers[L][0] / layers[L][1], 2) if L in layers else None for L in range(top + 1)]
        if sum(t is not None for t in temps) < 2: continue
        out.append([int(ym[:4]), int(ym[5:7]), round((i + 0.5) * DLAT, 4), round((j + 0.5) * DLON, 4), temps])
    data = {"fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
            "source": "eMOLT and MCFA profiling readings via erddap.emolt.net", "grid": [DLAT, DLON], "dz": DZ, "profiles": out}
    path = pathlib.Path(__file__).with_name("profiles.json")
    path.write_text(json.dumps(data, separators=(",", ":")))
    print(f"wrote {len(out)} square-month profiles from {len(jobs)} windows to {path}")


if __name__ == "__main__":
    main()
