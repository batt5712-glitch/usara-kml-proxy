import json
import os
import threading
import urllib.request
from flask import Flask, Response, abort, request

app = Flask(__name__)

TEAMS_URL = "https://live.enabledtracking.com/usara2026/data/teams-p26.json"
DEFAULT_TEAM = os.environ.get("DEFAULT_TEAM", "Team Unleashed")

_breadcrumbs = []  # list of (lat, lon, timestamp_str)
_breadcrumb_lock = threading.Lock()


def fetch_teams():
    req = urllib.request.Request(TEAMS_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def find_team(data, name):
    for cls in data.get("data", []):
        for t in cls.get("teams", []):
            if t["n"] == name:
                return t, cls
    return None, None


def record_breadcrumb(lat, lon, timestamp):
    with _breadcrumb_lock:
        if _breadcrumbs:
            last_lat, last_lon, _ = _breadcrumbs[-1]
            # Skip if moved less than ~10 meters (team is stopped)
            if abs(lat - last_lat) < 0.00009 and abs(lon - last_lon) < 0.00009:
                return
        _breadcrumbs.append((lat, lon, timestamp))


def build_kml(team_name):
    data = fetch_teams()
    t, cls = find_team(data, team_name)
    if not t:
        return b'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Team not found</name></Document></kml>'

    lat, lon = map(float, t["ll"].split(","))
    record_breadcrumb(lat, lon, t.get("lt", ""))

    status = "Active"
    if t.get("ret"):   status = "Retired"
    elif t.get("fin"): status = "Finished"
    elif t.get("st") == "signal-slash": status = "⚠ Signal lost"
    elif t.get("st") == "tools":        status = "🛠 Assist requested"

    desc = f"""<![CDATA[
<b style="font-size:14px">{t['n']}</b><br>
<hr style="margin:4px 0">
<b>Rank:</b> #{t['r']} ({cls.get('classname','')})<br>
<b>Checkpoint:</b> {t.get('lc','—')}<br>
<b>Elapsed:</b> {t.get('t','—')}<br>
<b>Speed:</b> {t.get('sp','0')} mph<br>
<b>Battery:</b> {t.get('b','?')}%<br>
<b>Status:</b> {status}<br>
<b>Updated:</b> {t.get('lt','—')}<br>
<hr style="margin:4px 0">
<i>{lat:.6f}, {lon:.6f}</i>
]]>"""

    kml = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{team_name} — USARA 2026</name>
    <Style id="s">
      <IconStyle>
        <color>ff3e88f0</color>
        <scale>1.3</scale>
        <Icon><href>http://maps.google.com/mapfiles/kml/paddle/wht-stars.png</href></Icon>
        <hotSpot x="0.5" y="0" xunits="fraction" yunits="fraction"/>
      </IconStyle>
      <LabelStyle><color>ff3e88f0</color><scale>1.0</scale></LabelStyle>
    </Style>
    <Placemark>
      <name>{team_name}</name>
      <styleUrl>#s</styleUrl>
      <description>{desc}</description>
      <Point>
        <altitudeMode>clampToGround</altitudeMode>
        <coordinates>{lon},{lat},0</coordinates>
      </Point>
    </Placemark>
  </Document>
</kml>'''
    return kml.encode()


def build_breadcrumbs_kml():
    with _breadcrumb_lock:
        crumbs = list(_breadcrumbs)

    if len(crumbs) < 2:
        kml = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{DEFAULT_TEAM} Track — USARA 2026</name>
    <description>Tracking started — building trail ({len(crumbs)} point so far)</description>
  </Document>
</kml>'''
        return kml.encode()

    coords = "\n".join(f"        {lon},{lat},0" for lat, lon, _ in crumbs)
    kml = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{DEFAULT_TEAM} Track — USARA 2026</name>
    <Style id="track">
      <LineStyle>
        <color>ff3e88f0</color>
        <width>3</width>
      </LineStyle>
    </Style>
    <Placemark>
      <name>{DEFAULT_TEAM} Track ({len(crumbs)} pts)</name>
      <styleUrl>#track</styleUrl>
      <LineString>
        <altitudeMode>clampToGround</altitudeMode>
        <tessellate>1</tessellate>
        <coordinates>
{coords}
        </coordinates>
      </LineString>
    </Placemark>
  </Document>
</kml>'''
    return kml.encode()


@app.route("/live.kml")
def live_kml():
    try:
        kml = build_kml(DEFAULT_TEAM)
        return Response(kml, mimetype="application/vnd.google-earth.kml+xml",
                        headers={"Cache-Control": "no-cache, no-store"})
    except Exception as e:
        abort(502, str(e))


@app.route("/breadcrumbs.kml")
def breadcrumbs_kml():
    return Response(build_breadcrumbs_kml(),
                    mimetype="application/vnd.google-earth.kml+xml",
                    headers={"Cache-Control": "no-cache, no-store"})


@app.route("/track.kml")
def track_kml():
    proto = request.headers.get("X-Forwarded-Proto", "https")
    host = f"{proto}://{request.host}"
    kml = f'''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{DEFAULT_TEAM} — USARA 2026 (Live)</name>
    <NetworkLink>
      <name>Current Position</name>
      <open>1</open>
      <Link>
        <href>{host}/live.kml</href>
        <refreshMode>onInterval</refreshMode>
        <refreshInterval>30</refreshInterval>
      </Link>
    </NetworkLink>
    <NetworkLink>
      <name>Trail</name>
      <open>1</open>
      <Link>
        <href>{host}/breadcrumbs.kml</href>
        <refreshMode>onInterval</refreshMode>
        <refreshInterval>60</refreshInterval>
      </Link>
    </NetworkLink>
  </Document>
</kml>'''
    return Response(kml.encode(), mimetype="application/vnd.google-earth.kml+xml",
                    headers={"Cache-Control": "no-cache, no-store"})


@app.route("/")
def index():
    with _breadcrumb_lock:
        n = len(_breadcrumbs)
    return (f"<h2>USARA 2026 Race Tracker</h2>"
            f"<p>Tracking: <b>{DEFAULT_TEAM}</b></p>"
            f"<p>Trail points recorded: <b>{n}</b></p>"
            f"<p><a href='/track.kml'>track.kml</a> — add as a Network Link in Google Earth Pro<br>"
            f"Current position refreshes every 30s · Trail refreshes every 60s</p>")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    app.run(host="0.0.0.0", port=port)
