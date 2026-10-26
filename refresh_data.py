"""Rebuild snapshot.json (bottom) and profiles.json (water column) from every useful fishing-industry source.

All averaging happens server side in ERDDAP (orderByMean / orderByCount), binned to 1 nm squares
(1 minute of latitude by 0.0225 deg of longitude, about 1 nm at 42 N) and calendar months; profiles are
also binned into 5 m layers. Run once a day (see .github/workflows/refresh.yml).

Usage:  python3 refresh_data.py            standard library only
"""
import csv, io, json, math, datetime, pathlib, urllib.parse, urllib.request, urllib.error, concurrent.futures as cf

EMOLT = "https://erddap.emolt.net/erddap/tabledap/"
ONDECK = "https://erddap.ondeckdata.com/erddap/tabledap/"
AREA = dict(latMin=40.3, latMax=45.2, lonMin=-74.0, lonMax=-65.5)
DLAT, DLON, DZ = 1 / 60, 0.0225, 5
BOTTOM_YEARS, PROFILE_MONTHS = 3, 12

# id, label, url, extra constraints, depth variables in order of preference
BOTTOM = [
    ("emolt", "eMOLT", EMOLT + "eMOLT_RT", ["segment_type=3"], ["depth"]),
    ("mcfa", "MCFA", EMOLT + "MCFA_RT", ["segment_type=3"], ["depth"]),
    ("cfrf_fixed", "CFRF fixed gear", ONDECK + "fixed_gear_oceanography", [], ["sea_pressure", "depth"]),
    ("gliders", "Demersal gliders", ONDECK + "demersal_gliders_aggregated", [], ["depth"]),
    ("sfw_receivers", "South Fork Wind receivers", ONDECK + "wind_farm_acoustic_receivers", [], ["depth"]),
]
PROFILES = [
    ("emolt", "eMOLT", EMOLT + "eMOLT_RT", ["segment_type<=2"], "depth"),
    ("mcfa", "MCFA", EMOLT + "MCFA_RT", ["segment_type<=2"], "depth"),
    ("cfrf_mobile", "CFRF trap casts", ONDECK + "mobile_gear_oceanography", [], "pressure"),
    ("shelf_fleet", "CFRF/WHOI Shelf Research Fleet CTD", ONDECK + "shelf_fleet_profiles_1m_binned", [], "sea_pressure"),
    ("sfw_ctd", "South Fork Wind survey CTD", ONDECK + "wind_farm_profiles_1m_binned", [], "sea_pressure"),
]
SOURCE_IDS = ["emolt", "mcfa", "cfrf_fixed", "gliders", "sfw_receivers", "cfrf_mobile", "shelf_fleet", "sfw_ctd"]
LABELS = {s[0]: s[1] for s in BOTTOM + PROFILES}
BIT = {sid: 1 << i for i, sid in enumerate(SOURCE_IDS)}


def months_back(n):
    t = datetime.date.today().replace(day=1)
    y, m = t.year, t.month - (n - 1)
    while m <= 0: y, m = y - 1, m + 12
    return y, m


def windows(start_ym, span):
    """Yield [t0, t1] windows of `span` months from start_ym through the current month."""
    t = datetime.date.today()
    y, m = start_ym
    while (y, m) <= (t.year, t.month):
        y2, m2 = y, m + span - 1
        while m2 > 12: y2, m2 = y2 + 1, m2 - 12
        if (y2, m2) > (t.year, t.month): y2, m2 = t.year, t.month
        end = datetime.date(y2 + (m2 == 12), m2 % 12 + 1, 1) - datetime.timedelta(days=1)
        yield f"{y}-{m:02d}-01", end.isoformat() + "T23:59:59Z"
        y, m = (y2, m2 + 1) if m2 < 12 else (y2 + 1, 1)


def query(base, variables, cons, agg):
    parts = [variables, f"latitude>={AREA['latMin']}", f"latitude<={AREA['latMax']}",
             f"longitude>={AREA['lonMin']}", f"longitude<={AREA['lonMax']}", *cons, agg]
    url = base + ".csv?" + "&".join(urllib.parse.quote(p, safe=",=/") for p in parts)
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "species-temperature-band-map/1.0"})
            with urllib.request.urlopen(req, timeout=600) as r:
                rows = list(csv.reader(io.TextIOWrapper(r, encoding="latin-1")))
                return rows[0], rows[2:]
        except urllib.error.HTTPError as e:
            if e.code == 404: return None, []  # ERDDAP answers 404 when a window has no rows
            if attempt == 2: print(f"  ! {base.rsplit('/',1)[1]} {e.code} for {cons}"); return None, []
        except Exception as e:
            if attempt == 2: print(f"  ! {base.rsplit('/',1)[1]} {e} for {cons}"); return None, []


def num(s):
    try:
        v = float(s); return None if math.isnan(v) else v
    except (TypeError, ValueError): return None


def bottom_job(src, t0, t1):
    sid, _, base, extra, zvars = src
    variables = ",".join(["time", "latitude", "longitude", *zvars, "temperature"])
    grp = f'("time/1month,latitude/{DLAT:.6f},longitude/{DLON}")'
    cons = [f"time>={t0}", f"time<={t1}", *extra]
    hm, means = query(base, variables, cons, "orderByMean" + grp)
    hc, counts = query(base, variables, cons, "orderByCount" + grp)
    if not means: return sid, []
    ix = {n: i for i, n in enumerate(hm)}
    cnt = {}
    if counts:
        ic = {n: i for i, n in enumerate(hc)}
        for r in counts: cnt[(r[0], r[1], r[2])] = int(float(r[ic["temperature"]]))
    out = []
    for r in means:
        t = num(r[ix["temperature"]])
        if t is None: continue
        z = next((num(r[ix[v]]) for v in zvars if num(r[ix[v]]) is not None), None)
        out.append((r[0][:7], int(float(r[1])), int(float(r[2])), t, z, cnt.get((r[0], r[1], r[2]), 1)))
    return sid, out


def profile_job(src, t0, t1):
    sid, _, base, extra, zvar = src
    grp = f'("time/1month,latitude/{DLAT:.6f},longitude/{DLON},{zvar}/{DZ}")'
    h, rows = query(base, f"time,latitude,longitude,{zvar},temperature", [f"time>={t0}", f"time<={t1}", *extra], "orderByMean" + grp)
    out = []
    for r in rows:
        t, L = num(r[4]), num(r[3])
        if t is None or L is None or L < 0: continue
        out.append((r[0][:7], int(float(r[1])), int(float(r[2])), int(L), t))
    return sid, out


def center(i, j): return round((i + 0.5) * DLAT, 4), round((j + 0.5) * DLON, 4)


def build_bottom(ex):
    jobs = [(s, *w) for s in BOTTOM for w in windows((datetime.date.today().year - BOTTOM_YEARS + 1, 1), 6)]
    acc = {}
    for sid, rows in ex.map(lambda j: bottom_job(*j), jobs):
        for ym, i, j, t, z, n in rows:
            a = acc.setdefault((ym, i, j), [0.0, 0.0, 0, 0, 0])
            a[0] += t * n; a[2] += n; a[4] |= BIT[sid]
            if z is not None: a[1] += z * n; a[3] += n
    obs = []
    for (ym, i, j), (st, sz, n, nz, mask) in sorted(acc.items()):
        la, lo = center(i, j)
        obs.append([int(ym[:4]), int(ym[5:7]), la, lo, round(st / n, 2), round(sz / nz) if nz else None, n, mask])
    return obs


def build_profiles(ex):
    jobs = [(s, *w) for s in PROFILES for w in windows(months_back(PROFILE_MONTHS), 3)]
    acc = {}
    for sid, rows in ex.map(lambda j: profile_job(*j), jobs):
        for ym, i, j, L, t in rows:
            cell = acc.setdefault((ym, i, j), [{}, 0])
            a = cell[0].setdefault(L, [0.0, 0]); a[0] += t; a[1] += 1
            cell[1] |= BIT[sid]
    out = []
    for (ym, i, j), (layers, mask) in sorted(acc.items()):
        top = max(layers)
        temps = [round(layers[L][0] / layers[L][1], 2) if L in layers else None for L in range(top + 1)]
        if sum(t is not None for t in temps) < 2: continue
        la, lo = center(i, j)
        out.append([int(ym[:4]), int(ym[5:7]), la, lo, temps, mask])
    return out


def main():
    here = pathlib.Path(__file__).parent
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")
    meta = {"fetched": now, "grid": [DLAT, DLON], "sources": [[sid, LABELS[sid]] for sid in SOURCE_IDS]}
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        obs = build_bottom(ex)
        prof = build_profiles(ex)
    (here / "snapshot.json").write_text(json.dumps({**meta, "obs": obs}, separators=(",", ":")))
    (here / "profiles.json").write_text(json.dumps({**meta, "dz": DZ, "profiles": prof}, separators=(",", ":")))
    for name, rows, k in (("bottom", obs, 7), ("profile", prof, 5)):
        tally = {sid: sum(1 for r in rows if r[k] & BIT[sid]) for sid in SOURCE_IDS}
        print(f"{name}: {len(rows)} square-months; by source {({k2: v for k2, v in tally.items() if v})}")


if __name__ == "__main__":
    main()
