"""
refs #2515 Phase 0: multiParty call の participantList 分析スクリプト

Teams の IndexedDB から出力した JSON を読み込み、
multiParty call（グループ通話/会議）の participantList に
実参加者が含まれているかを確認する。

使い方:
  1. ms_teams_parser.exe で JSON を出力:
     ms_teams_parser.exe -f "%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\EBWebView\Default\IndexedDB\https_teams.microsoft.com_0.indexeddb.leveldb" -o C:\tmp\teams_output.json

  2. 本スクリプトを実行:
     python analyze_multiparty_calls.py C:\tmp\teams_output.json
"""
import json
import sys


def get_call_log(call):
    """call-log または callLog キーから callLog を取得する"""
    props = call.get("properties", {})
    return props.get("call-log", props.get("callLog", {})) or {}


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_multiparty_calls.py <teams_output.json>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    contacts = {r["mri"]: r for r in data if r.get("record_type") == "contact"}
    calls = [r for r in data if r.get("record_type") == "call"]
    meetings = [r for r in data if r.get("record_type") == "meeting"]

    print(f"=== Summary: {len(contacts)} contacts, {len(calls)} calls, {len(meetings)} meetings ===\n")

    # --- call レコードの概要 ---
    print("--- call レコードの概要（最初の3件）---\n")
    for i, c in enumerate(calls[:3]):
        cl = get_call_log(c)
        print(f"call {i+1}:")
        print(f"  callLog keys: {list(cl.keys())[:20]}")
        print(f"  callState:     {cl.get('callState')}")
        print(f"  callType:      {cl.get('callType')}")
        print(f"  callDirection: {cl.get('callDirection')}")
        print(f"  startTime:     {cl.get('startTime')}")
        print(f"  endTime:       {cl.get('endTime')}")
        plist = cl.get("participantList", [])
        participants = cl.get("participants", [])
        print(f"  participantList: {len(plist) if plist else 'None'}")
        print(f"  participants:    {len(participants) if participants else 'None'}")
        print()

    # --- callType 集計 ---
    call_types = {}
    for c in calls:
        cl = get_call_log(c)
        ct = cl.get("callType", "N/A")
        call_types[ct] = call_types.get(ct, 0) + 1
    print(f"--- callType 集計 ---")
    for ct, count in sorted(call_types.items(), key=lambda x: -x[1]):
        print(f"  {ct}: {count} 件")
    print()

    # --- callState 集計 ---
    call_states = {}
    for c in calls:
        cl = get_call_log(c)
        cs = cl.get("callState", "N/A")
        call_states[cs] = call_states.get(cs, 0) + 1
    print(f"--- callState 集計 ---")
    for cs, count in sorted(call_states.items(), key=lambda x: -x[1]):
        print(f"  {cs}: {count} 件")
    print()

    # --- multiParty calls ---
    mp_calls = [c for c in calls if get_call_log(c).get("callType") == "multiParty"]
    print(f"--- multiParty calls: {len(mp_calls)} 件 ---\n")

    # --- participantList を持つ call ---
    has_plist = [c for c in calls if get_call_log(c).get("participantList")]
    has_participants = [c for c in calls if get_call_log(c).get("participants")]
    print(f"--- participantList を持つ call: {len(has_plist)} 件 ---")
    print(f"--- participants を持つ call: {len(has_participants)} 件 ---\n")

    def find_contact(pid):
        if not pid:
            return None
        ct = contacts.get(pid)
        if ct:
            return ct
        uuid = pid.split(":")[-1] if isinstance(pid, str) and ":" in pid else pid
        for k, v in contacts.items():
            if uuid and uuid in k:
                return v
        return None

    # participantList がある call の詳細
    for i, c in enumerate((mp_calls or has_plist or has_participants)[:10]):
        cl = get_call_log(c)
        print(f"--- call {i+1} ---")
        print(f"  startTime:     {cl.get('startTime')}")
        print(f"  endTime:       {cl.get('endTime')}")
        print(f"  callState:     {cl.get('callState')}")
        print(f"  callType:      {cl.get('callType')}")
        print(f"  callDirection: {cl.get('callDirection')}")

        plist = cl.get("participantList", [])
        participants = cl.get("participants", [])

        if plist:
            print(f"  participantList ({len(plist)}):")
            for p in plist:
                pid = p.get("id", p) if isinstance(p, dict) else p
                ct = find_contact(pid)
                name = ct.get("displayName", "?") if ct else "?"
                email = ct.get("email", "no email") if ct else "no email"
                print(f"    {pid} -> {name} ({email})")

        if participants:
            print(f"  participants ({len(participants)}):")
            for p in participants:
                ct = find_contact(p)
                name = ct.get("displayName", "?") if ct else "?"
                email = ct.get("email", "no email") if ct else "no email"
                print(f"    {p} -> {name} ({email})")

        print()

    # --- meetings の members 情報 ---
    print(f"--- meetings の概要（最初の5件）---\n")
    for i, m in enumerate(meetings[:5]):
        tp = m.get("threadProperties", {}).get("meeting", {})
        members = m.get("members", [])
        print(f"meeting {i+1}:")
        print(f"  subject:   {tp.get('subject', 'N/A')}")
        print(f"  startTime: {tp.get('startTime')}")
        print(f"  endTime:   {tp.get('endTime')}")
        print(f"  members ({len(members)}):")
        for mem in members[:10]:
            mid = mem.get("id", str(mem))
            ct = find_contact(mid)
            name = ct.get("displayName", "?") if ct else "?"
            email = ct.get("email", "no email") if ct else "no email"
            print(f"    {mid} -> {name} ({email})")
        if len(members) > 10:
            print(f"    ... 他 {len(members) - 10} 人")
        print()


if __name__ == "__main__":
    main()
