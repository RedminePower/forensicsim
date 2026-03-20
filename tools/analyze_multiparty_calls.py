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

    # --- multiParty calls ---
    mp_calls = [c for c in calls
                if c.get("properties", {}).get("callLog", {}).get("callType") == "multiParty"]

    print(f"--- multiParty calls: {len(mp_calls)} 件 ---\n")

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

    for i, c in enumerate(mp_calls[:10]):
        cl = c["properties"]["callLog"]
        print(f"--- call {i+1} ---")
        print(f"  startTime:     {cl.get('startTime')}")
        print(f"  endTime:       {cl.get('endTime')}")
        print(f"  callState:     {cl.get('callState')}")
        print(f"  callDirection: {cl.get('callDirection')}")
        print(f"  threadId:      {cl.get('threadId', 'N/A')}")

        plist = cl.get("participantList", [])
        participants = cl.get("participants", [])

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

    # --- meetings との比較 ---
    if mp_calls and meetings:
        print("--- 同時間帯の meeting との比較 ---\n")
        for i, c in enumerate(mp_calls[:5]):
            cl = c["properties"]["callLog"]
            call_start = cl.get("startTime", "")
            call_thread = cl.get("threadId", "")

            matching_meetings = []
            for m in meetings:
                tp = m.get("threadProperties", {}).get("meeting", {})
                # threadId で照合
                if call_thread and call_thread == m.get("id"):
                    matching_meetings.append(m)

            if matching_meetings:
                print(f"  call {i+1} ({call_start}) に対応する meeting:")
                for m in matching_meetings:
                    tp = m.get("threadProperties", {}).get("meeting", {})
                    members = m.get("members", [])
                    plist = cl.get("participantList", [])
                    print(f"    subject: {tp.get('subject', 'N/A')}")
                    print(f"    meeting members: {len(members)} 人, call participantList: {len(plist)} 人")
                    print(f"    → 差分があれば meeting=招待者全員, call=実参加者 の可能性が高い")
                print()

    if not mp_calls:
        print("multiParty call が 0 件です。")
        print("通常の call レコードの callType 一覧:")
        call_types = {}
        for c in calls:
            ct = c.get("properties", {}).get("callLog", {}).get("callType", "N/A")
            call_types[ct] = call_types.get(ct, 0) + 1
        for ct, count in sorted(call_types.items(), key=lambda x: -x[1]):
            print(f"  {ct}: {count} 件")


if __name__ == "__main__":
    main()
