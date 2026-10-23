import json
import os
import urllib.request
from flask import Flask, Response, abort

app = Flask(__name__)

TEAMS_URL = "https://live.enabledtracking.com/usara2026/data/teams-p26.json"
DEFAULT_TEAM = os.environ.get("DEFAULT_TEAM", "Team Unleashed")


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


def build_kml(team_name):
    data = fetch_teams()
    t, cls = find_team(data, team_name)
    if not t:
        return b'<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Team not found</name></Document></kml>'

    lat, lon = map(float, t["ll"].split(","))

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


@app.route("/live.kml")
def live_kml():
    team = DEFAULT_TEAM
    try:
        kml = build_kml(team)
        return Response(kml,
                        mimetype="application/vnd.google-earth.kml+xml",
                        headers={"Cache-Control": "no-cache, no-store"})
    except Exception as e:
        abort(502, str(e))


@app.route("/")
def index():
    return (f"<h2>USARA 2026 Race Tracker</h2>"
            f"<p>Tracking: <b>{DEFAULT_TEAM}</b></p>"
            f"<p><a href='/live.kml'>live.kml</a> — add this URL as a Network Link in Google Earth Pro "
            f"(refresh interval: 30s)</p>")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    app.run(host="0.0.0.0", port=port)
