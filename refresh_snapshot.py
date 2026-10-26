"""Rebuild snapshot.json: 1 nm bottom-temperature squares from eMOLT and MCFA fishing-vessel sensors.

Readings are fishing segments only (segment_type=3, gear on or near the bottom), QC-flagged good by the
providers. ERDDAP bins them server side to 1 minute of latitude (1 nm) by 0.0225 deg of longitude
(about 1 nm at 42 N) and to calendar months, then this script combines the two sources.
Usage:  python3 refresh_snapshot.py     (standard library only)
"""
import csv, io, json, datetime, pathlib, urllib.parse, urllib.request, concurrent.futures as cf

SOURCES = ["https://erddap.emolt.net/erddap/tabledap/eMOLT_RT", "https://erddap.emolt.net/erddap/tabledap/MCFA_RT"]
AREA = dict(latMin=40.3, latMax=45.2, lonMin=-74.0, lonMax=-65.5)
DLAT, DLON = 1 / 60, 0.0225
START_YEAR = datetime.date.today().year - 2


def chunks():
    today = datetime.date.today()
    y, h = START_YEAR, 0
    while (y, h * 6 + 1) <= (today.year, today.month):
        a = datetime.date(y, h * 6 + 1, 1)
        b = datetime.date(y, 6, 30) if h == 0 else datetime.date(y, 12, 31)
        yield a.isoformat(), b.isoformat() + "T23:59:59Z"
        y, h = (y, 1) if h == 0 else (y + 1, 0)


def query(base, agg, t0, t1):
    parts = ["time,latitude,longitude,depth,temperature",
             f"latitude>={AREA['latMin']}", f"latitude<={AREA['latMax']}",
             f"longitude>={AREA['lonMin']}", f"longitude<={AREA['lonMax']}",
             f"time>={t0}", f"time<={t1}", "segment_type=3",
             f'{agg}("time/1month,latitude/{DLAT:.6f},longitude/{DLON}")']
    url = base + ".csv?" + "&".join(urllib.parse.quote(p, safe=",=/") for p in parts)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "species-temperature-band-map/1.0"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return list(csv.reader(io.TextIOWrapper(r, encoding="latin-1")))[2:]
        except urllib.error.HTTPError as e:
            if e.code == 404:  # ERDDAP returns 404 when a window has no rows
                return []
            if attempt == 2: raise
        except Exception:
            if attempt == 2: raise


def main():
    jobs = [(s, t0, t1) for s in SOURCES for t0, t1 in chunks()]
    acc = {}
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        res = list(ex.map(lambda j: (query(j[0], "orderByMean", j[1], j[2]), query(j[0], "orderByCount", j[1], j[2])), jobs))
    for means, counts in res:
        cnt = {(t, la, lo): int(float(n)) for t, la, lo, _z, n in counts}
        for t, la, lo, z, temp in means:
            if not temp or temp == "NaN": continue
            n = cnt.get((t, la, lo), 1)
            key = (t[:7], int(float(la)), int(float(lo)))
            a = acc.setdefault(key, [0.0, 0.0, 0])
            a[0] += float(temp) * n; a[1] += (float(z) if z and z != "NaN" else 0) * n; a[2] += n
    obs = []
    for (ym, i, j), (st, sz, n) in sorted(acc.items()):
        obs.append([int(ym[:4]), int(ym[5:7]), round((i + 0.5) * DLAT, 4), round((j + 0.5) * DLON, 4),
                    round(st / n, 2), round(sz / n), n])
    out = {"fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes"),
           "source": "eMOLT and MCFA bottom readings via erddap.emolt.net, 1 nm bins", "grid": [DLAT, DLON], "obs": obs}
    path = pathlib.Path(__file__).with_name("snapshot.json")
    path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {len(obs)} square-months from {len(jobs)} windows to {path}")


if __name__ == "__main__":
    main()
