"""Rebuild snapshot.json (bottom) and profiles.json (water column) from every useful fishing-industry source.

ERDDAP averages each source server side (orderByMean / orderByCount) into fine 1 nm bins and calendar months
(profiles also into 5 m layers). This script then snaps every fine bin onto the FIShBOT 7 km grid, using the cell
definitions in fishbot_grid.json (FIShBOT's botgrid: UTM zone 19N, 7000 m cells), and combines the sources.
It also writes grid.json with the corners of every cell that has data. Run once a day (see
.github/workflows/refresh.yml).

Usage:  python3 refresh_data.py            standard library only
"""
import csv, io, json, math, datetime, pathlib, urllib.parse, urllib.request, urllib.error, concurrent.futures as cf

EMOLT = "https://erddap.emolt.net/erddap/tabledap/"
ONDECK = "https://erddap.ondeckdata.com/erddap/tabledap/"
COMET = "https://comet.nefsc.noaa.gov/erddap/tabledap/"
GLIDERS = "https://gliders.ioos.us/erddap/"
DMF = "https://services1.arcgis.com/7iJyYTjCtKsZS1LR/arcgis/rest/services/"
AREA = dict(latMin=40.3, latMax=45.2, lonMin=-74.0, lonMax=-65.5)
DLAT, DLON, DZ = 1 / 60, 0.0225, 5   # fine bins from ERDDAP before snapping to the FIShBOT grid
BOTTOM_YEARS, PROFILE_MONTHS = 3, 12

# id, label, url, extra constraints, depth variables in order of preference
BOTTOM = [
    ("emolt", "eMOLT", EMOLT + "eMOLT_RT", ["segment_type=3"], ["depth"]),
    ("mcfa", "MCFA", EMOLT + "MCFA_RT", ["segment_type=3"], ["depth"]),
    ("cfrf_fixed", "CFRF fixed gear", ONDECK + "fixed_gear_oceanography", [], ["sea_pressure", "depth"]),
    ("gliders", "Demersal gliders", ONDECK + "demersal_gliders_aggregated", [], ["depth"]),
    ("sfw_receivers", "South Fork Wind receivers", ONDECK + "wind_farm_acoustic_receivers", [], ["depth"]),
]
# id, label, url, extra constraints, depth variable, time variable, temperature variable
PROFILES = [
    ("emolt", "eMOLT", EMOLT + "eMOLT_RT", ["segment_type<=2"], "depth", "time", "temperature"),
    ("mcfa", "MCFA", EMOLT + "MCFA_RT", ["segment_type<=2"], "depth", "time", "temperature"),
    ("cfrf_mobile", "CFRF trap casts", ONDECK + "mobile_gear_oceanography", [], "pressure", "time", "temperature"),
    ("shelf_fleet", "CFRF/WHOI Shelf Research Fleet CTD", ONDECK + "shelf_fleet_profiles_1m_binned", [], "sea_pressure", "time", "temperature"),
    ("sfw_ctd", "South Fork Wind survey CTD", ONDECK + "wind_farm_profiles_1m_binned", [], "sea_pressure", "time", "temperature"),
    ("ecomon", "NOAA NEFSC ECOMON and survey CTD", COMET + "ocdbs_v_erddap1", ['GEAR_TYPE!="Bottle"'], "depth", "UTC_DATETIME", "sea_water_temperature"),
]
# Mass. DMF ArcGIS layers (bottom): Cape Cod Bay Study Fleet DO loggers in lobster traps, and DMF fixed bottom stations
DMF_DO_LAYERS = ["DMF_Avg_DO_PublicView", "DMF_Avg_DO_2024_Archive", "DMF_Avg_DO_2023_Archive"]
DMF_STATIONS = {  # table column -> location name in layer 3 (station depths are in feet)
    "Cleveland_25": "Cleveland", "Bbay_Barge_Tower_70": "BBay Barge", "Rocky_45": "Rocky Point", "Manomet_55": "Manomet",
    "Mars_110": "Mars", "Martins_Romance_70": "Martins Ledge", "Sippewissett_18": "Sippewisset", "Scortons_30": "Scorton",
    "Cuttyhunk_18": "Cuttyhunk"}
SOURCE_IDS = ["emolt", "mcfa", "cfrf_fixed", "gliders", "sfw_receivers", "cfrf_mobile", "shelf_fleet", "sfw_ctd",
              "ecomon", "ioos_gliders", "dmf_do", "dmf_stations"]
LABELS = {s[0]: s[1] for s in BOTTOM + PROFILES}
LABELS.update({"ioos_gliders": "IOOS Glider DAC profiles", "dmf_do": "Mass. DMF Cape Cod Bay DO study fleet",
               "dmf_stations": "Mass. DMF bottom temperature stations"})
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
    sid, _, base, extra, zvar, tvar, tempvar = src
    grp = f'("{tvar}/1month,latitude/{DLAT:.6f},longitude/{DLON},{zvar}/{DZ}")'
    h, rows = query(base, f"{tvar},latitude,longitude,{zvar},{tempvar}", [f"{tvar}>={t0}", f"{tvar}<={t1}", f"{tempvar}>-3", f"{tempvar}<35", *extra], "orderByMean" + grp)
    out = []
    for r in rows:
        t, L = num(r[4]), num(r[3])
        if t is None or L is None or L < 0: continue
        out.append((r[0][:7], int(float(r[1])), int(float(r[2])), int(L), t))
    return sid, out


def utm19(lat, lon):
    """WGS84 lat/lon -> UTM zone 19N easting, northing (Kruger series, mm accuracy)."""
    a=6378137.0; f=1/298.257223563; k0=0.9996; lon0=math.radians(-69.0)
    n=f/(2-f); A=a/(1+n)*(1+n*n/4+n**4/64)
    al=[None, n/2-2*n*n/3+5*n**3/16, 13*n*n/48-3*n**3/5, 61*n**3/240]
    e=math.sqrt(f*(2-f)); phi=math.radians(lat); lam=math.radians(lon)-lon0
    t=math.sinh(math.atanh(math.sin(phi))-2*math.sqrt(n)/(1+n)*math.atanh(2*math.sqrt(n)/(1+n)*math.sin(phi)))
    xi=math.atan2(t,math.cos(lam)); eta=math.atanh(math.sin(lam)/math.sqrt(1+t*t))
    E=500000+k0*A*(eta+sum(al[j]*math.cos(2*j*xi)*math.sinh(2*j*eta) for j in (1,2,3)))
    N=k0*A*(xi+sum(al[j]*math.sin(2*j*xi)*math.cosh(2*j*eta) for j in (1,2,3)))
    return E,N


GRID = json.loads((pathlib.Path(__file__).parent / "fishbot_grid.json").read_text())
CELL = {(c[1], c[2]): c for c in GRID["cells"]}   # (row, col) -> [id, row, col, lat, lon, corners]
BYID = {c[0]: c for c in GRID["cells"]}


def cell_of_ll(lat, lon):
    """FIShBOT cell containing a point, or None if outside the grid."""
    E, N = utm19(lat, lon)
    return CELL.get((int((GRID["N0"] - N) // GRID["size"]), int((E - GRID["E0"]) // GRID["size"])))


def cell_of(i, j):
    """FIShBOT cell containing the centre of fine bin (i, j)."""
    return cell_of_ll((i + 0.5) * DLAT, (j + 0.5) * DLON)


def get_json(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "species-temperature-band-map/1.0"})
            with urllib.request.urlopen(req, timeout=300) as r: return json.load(r)
        except Exception as e:
            if attempt == 2: print(f"  ! {url[:90]} {e}"); return {}


def arcgis_rows(layer_url, where, fields, geometry):
    """Page through an ArcGIS feature layer or table query."""
    out, offset = [], 0
    while True:
        q = {"where": where, "outFields": fields, "returnGeometry": "true" if geometry else "false", "outSR": "4326",
             "resultOffset": offset, "resultRecordCount": 2000, "orderByFields": "OBJECTID", "f": "json"}
        d = get_json(layer_url + "/query?" + urllib.parse.urlencode(q))
        feats = d.get("features", [])
        out += feats
        if not feats or not d.get("exceededTransferLimit"): return out
        offset += len(feats)


def dmf_bottom():
    """Mass. DMF bottom temperatures as (ym, lat, lon, temp, depth_m, n, sid) points."""
    start = f"{datetime.date.today().year - BOTTOM_YEARS + 1}-01-01"
    pts = []
    for layer in DMF_DO_LAYERS:
        for f in arcgis_rows(DMF + layer + "/FeatureServer/0", f"DateTime >= TIMESTAMP '{start} 00:00:00'", "DateTime,Avg_Temp_C,Avg_Ct", True):
            a, g = f["attributes"], f.get("geometry") or {}
            if a.get("Avg_Temp_C") is None or a.get("DateTime") is None or "x" not in g: continue
            d = datetime.datetime.fromtimestamp(a["DateTime"] / 1000, datetime.timezone.utc)
            pts.append((f"{d.year}-{d.month:02d}", g["y"], g["x"], float(a["Avg_Temp_C"]), None, int(a.get("Avg_Ct") or 1), "dmf_do"))
    st = DMF + "MA_Ocean_Bottom_Temperature_Sensor_Data/FeatureServer"
    loc = {f["attributes"]["Location"]: f["attributes"] for f in arcgis_rows(st + "/3", "1=1", "*", False)}
    for f in arcgis_rows(st + "/0", f"DATE >= TIMESTAMP '{start} 00:00:00'", "*", False):
        a = f["attributes"]
        if a.get("DATE") is None: continue
        d = datetime.datetime.fromtimestamp(a["DATE"] / 1000, datetime.timezone.utc)
        for col, name in DMF_STATIONS.items():
            v, s = a.get(col), loc.get(name)
            if v is None or s is None: continue
            pts.append((f"{d.year}-{d.month:02d}", s["Lat"], s["Long"], float(v), s["Depth"] * 0.3048, 1, "dmf_stations"))
    return pts


def glider_sources():
    """IOOS Glider DAC deployments in the area over the profile window (delayed-mode copy preferred)."""
    y, m = months_back(PROFILE_MONTHS)
    q = {"page": 1, "itemsPerPage": 1000, "searchFor": "", "protocol": "tabledap", "minLat": AREA["latMin"], "maxLat": AREA["latMax"],
         "minLon": AREA["lonMin"], "maxLon": AREA["lonMax"], "minTime": f"{y}-{m:02d}-01T00:00:00Z"}
    try:
        req = urllib.request.Request(GLIDERS + "search/advanced.csv?" + urllib.parse.urlencode(q), headers={"User-Agent": "species-temperature-band-map/1.0"})
        with urllib.request.urlopen(req, timeout=300) as r: rows = list(csv.reader(io.TextIOWrapper(r, encoding="utf-8")))
    except Exception as e:
        print(f"  ! glider search {e}"); return []
    ids = [x[rows[0].index("Dataset ID")] for x in rows[1:]]
    low = {i.lower() for i in ids}
    keep = [i for i in ids if i.endswith("-delayed") or (i.lower() + "-delayed") not in low]
    return [("ioos_gliders", LABELS["ioos_gliders"], GLIDERS + "tabledap/" + i, [], "depth", "time", "temperature") for i in keep]


def build_bottom(ex):
    jobs = [(s, *w) for s in BOTTOM for w in windows((datetime.date.today().year - BOTTOM_YEARS + 1, 1), 6)]
    acc = {}
    def add(sid, ym, c, t, z, n):
        a = acc.setdefault((ym, c[0]), [0.0, 0.0, 0, 0, 0])
        a[0] += t * n; a[2] += n; a[4] |= BIT[sid]
        if z is not None: a[1] += z * n; a[3] += n
    for sid, rows in ex.map(lambda j: bottom_job(*j), jobs):
        for ym, i, j, t, z, n in rows:
            c = cell_of(i, j)
            if c is not None: add(sid, ym, c, t, z, n)
    for ym, lat, lon, t, z, n, sid in dmf_bottom():
        c = cell_of_ll(lat, lon)
        if c is not None and -3 < t < 35: add(sid, ym, c, t, z, n)
    obs = []
    for (ym, cid), (st, sz, n, nz, mask) in sorted(acc.items()):
        la, lo = BYID[cid][3], BYID[cid][4]
        obs.append([int(ym[:4]), int(ym[5:7]), la, lo, round(st / n, 2), round(sz / nz) if nz else None, n, mask])
    return obs


def build_profiles(ex):
    y, m = months_back(PROFILE_MONTHS)
    jobs = [(s, *w) for s in PROFILES for w in windows((y, m), 3)]
    gl = glider_sources()
    print(f"  {len(gl)} glider deployments")
    jobs += [(s, f"{y}-{m:02d}-01", datetime.date.today().isoformat() + "T23:59:59Z") for s in gl]
    acc = {}
    for sid, rows in ex.map(lambda j: profile_job(*j), jobs):
        for ym, i, j, L, t in rows:
            c = cell_of(i, j)
            if c is None: continue
            cell = acc.setdefault((ym, c[0]), [{}, 0])
            a = cell[0].setdefault(L, [0.0, 0]); a[0] += t; a[1] += 1
            cell[1] |= BIT[sid]
    out = []
    for (ym, cid), (layers, mask) in sorted(acc.items()):
        top = max(layers)
        temps = [round(layers[L][0] / layers[L][1], 2) if L in layers else None for L in range(top + 1)]
        if sum(t is not None for t in temps) < 2: continue
        la, lo = BYID[cid][3], BYID[cid][4]
        out.append([int(ym[:4]), int(ym[5:7]), la, lo, temps, mask])
    return out


def main():
    here = pathlib.Path(__file__).parent
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="minutes")
    meta = {"fetched": now, "grid": "fishbot-7km", "sources": [[sid, LABELS[sid]] for sid in SOURCE_IDS]}
    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        obs = build_bottom(ex)
        prof = build_profiles(ex)
    (here / "snapshot.json").write_text(json.dumps({**meta, "obs": obs}, separators=(",", ":")))
    (here / "profiles.json").write_text(json.dumps({**meta, "dz": DZ, "profiles": prof}, separators=(",", ":")))
    used = {(r[2], r[3]) for r in obs} | {(r[2], r[3]) for r in prof}
    cells = [[c[3], c[4], c[0], c[5]] for c in GRID["cells"] if (c[3], c[4]) in used]
    (here / "grid.json").write_text(json.dumps({"fetched": now, "cells": cells}, separators=(",", ":")))
    for name, rows, k in (("bottom", obs, 7), ("profile", prof, 5)):
        tally = {sid: sum(1 for r in rows if r[k] & BIT[sid]) for sid in SOURCE_IDS}
        print(f"{name}: {len(rows)} square-months; by source {({k2: v for k2, v in tally.items() if v})}")


if __name__ == "__main__":
    main()
