"""Check call records in output.json"""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "output.json"
data = json.load(open(path, "r", encoding="utf-8"))

calls = [r for r in data if r.get("record_type") == "call"]
print(f"Total records: {len(data)}")
print(f"Call records: {len(calls)}")
print()

group = [
    c for c in calls
    if c.get("properties", {}).get("call-log", {}).get("callType") == "multiParty"
]
print(f"Group calls (multiParty): {len(group)}")
print()

if group:
    cl = group[0]["properties"]["call-log"]
    print("=== First group call ===")
    print(f"startTime:       {cl.get('startTime')}")
    print(f"endTime:         {cl.get('endTime')}")
    print(f"callDirection:   {cl.get('callDirection')}")
    print(f"callState:       {cl.get('callState')}")
    print(f"threadId:        {cl.get('threadId')}")
    print(f"participantList: {cl.get('participantList')}")
    print(f"participants:    {cl.get('participants')}")
    print()

    orig = cl.get("originatorParticipant", {})
    tgt = cl.get("targetParticipant", {})
    print(f"originator: {orig.get('displayName')} ({orig.get('id')})")
    print(f"target:     {tgt.get('displayName')} ({tgt.get('id')})")
    print()

    # Show full call-log JSON for first group call
    print("=== Full call-log JSON ===")
    print(json.dumps(cl, indent=2, ensure_ascii=False, default=str))
