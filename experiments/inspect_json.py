import json
from pathlib import Path

raw = Path("output/hands_video_teste_reduzido_20260521_090505.json").read_text(encoding="utf-8")
data = json.loads(raw)
for h in data["hands"]:
    if h.get("table_id") == "HL3048":
        flop = h["streets"]["flop"]
        turn = h["streets"].get("turn", [])
        print("flop type:", type(flop))
        keys = list(flop.keys())
        print("flop keys:", keys[:5])
        for k in keys[:3]:
            print(f"  flop[{k}]:", flop[k])
