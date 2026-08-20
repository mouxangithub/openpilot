#!/usr/bin/env python3
import json
import urllib.request
data = json.load(urllib.request.urlopen("http://127.0.0.1:5090/api/ai/publish", timeout=15))
for u in data.get("units") or []:
    print(u.get("id"), u.get("display_name"), u.get("git_root"))
