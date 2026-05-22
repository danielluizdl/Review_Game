import json, glob, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

jsons = sorted(glob.glob('output/hands_*.json'), key=os.path.getmtime)
fname = jsons[-1]
print(f'JSON: {fname}\n')

with open(fname, encoding='utf-8') as f:
    raw = json.load(f)

for h in raw['hands']:
    if 'HL3048' in str(h.get('table_id', '')):
        print("=== ALL ACTIONS ===")
        for a in h.get("actions", []):
            print(f"[{a.get('street').upper()}] {a.get('player')} ({a.get('position')}): {a.get('action')} {a.get('amount_bb')}bb (total={a.get('total_bb')}bb) | ts={a.get('ts')}")
        break
