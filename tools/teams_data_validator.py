"""
Teams データ検証スクリプト (Phase 0)
会社PCで ms_teams_parser.exe の出力JSONを解析し、
call/meeting レコードの参加者情報の信頼性を確認する。

使い方:
1. ms_teams_parser.exe で JSON を出力:
   cd C:\path\to\forensicsim\dist
   ms_teams_parser.exe -f "%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\EBWebView\Default\IndexedDB\https_teams.microsoft.com_0.indexeddb.leveldb" -o C:\tmp\teams_output.json

2. 本スクリプトを実行:
   python C:\tmp\teams_data_validator.py C:\tmp\teams_output.json
"""

import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def get_call_log(record):
    """call-log キーを取得する（パーサー出力は 'call-log'、TeamsService.cs は 'callLog'）"""
    props = record.get("properties", {})
    cl = props.get("call-log") or props.get("callLog") or {}
    if isinstance(cl, str):
        try:
            cl = json.loads(cl)
        except:
            cl = {}
    return cl if isinstance(cl, dict) else {}


def main():
    if len(sys.argv) < 2:
        print("Usage: python teams_data_validator.py <teams_output.json>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)

    contacts = {r["mri"]: r for r in data if r.get("record_type") == "contact"}
    calls = [r for r in data if r.get("record_type") == "call"]
    meetings = [r for r in data if r.get("record_type") == "meeting"]

    # email 充填率
    contacts_with_email = sum(1 for c in contacts.values() if c.get("email"))
    email_rate = contacts_with_email / len(contacts) * 100 if contacts else 0

    print(f"=== Summary ===")
    print(f"  contacts: {len(contacts)} (email充填率: {email_rate:.1f}% = {contacts_with_email}/{len(contacts)})")
    print(f"  calls:    {len(calls)}")
    print(f"  meetings: {len(meetings)}")

    # multiParty calls (= group meetings)
    mp_calls = [c for c in calls if get_call_log(c).get("callType") == "multiParty"]
    tp_calls = [c for c in calls if get_call_log(c).get("callType") == "twoParty"]
    print(f"\n--- Call breakdown ---")
    print(f"  multiParty: {len(mp_calls)}")
    print(f"  twoParty:   {len(tp_calls)}")

    print(f"\n--- multiParty calls (top 10) ---")
    for c in mp_calls[:10]:
        cl = get_call_log(c)
        print(f"\n  startTime: {cl.get('startTime')}")
        print(f"  endTime:   {cl.get('endTime')}")
        print(f"  callState: {cl.get('callState')}")
        print(f"  threadId:  {cl.get('threadId', 'N/A')}")
        plist = cl.get("participantList") or cl.get("participants") or []
        has_plist = cl.get("participantList") is not None
        has_parts = cl.get("participants") is not None
        print(f"  participantList存在: {has_plist} (値: {'null' if cl.get('participantList') is None else len(cl.get('participantList', []))}件)")
        print(f"  participants存在:    {has_parts} (値: {'null' if cl.get('participants') is None else len(cl.get('participants', []))}件)")
        if plist:
            print(f"  participants ({len(plist)}):")
            for p in plist[:20]:
                pid = p.get("id", p) if isinstance(p, dict) else p
                ct = contacts.get(pid, {})
                print(f"    {pid}")
                print(f"      displayName: {ct.get('displayName', '?')}")
                print(f"      email:       {ct.get('email', 'NO EMAIL')}")
        else:
            # originator/target で確認
            orig = cl.get("originatorParticipant", {})
            tgt = cl.get("targetParticipant", {})
            if orig:
                ct = contacts.get(orig.get("id"), {})
                print(f"  originator: {orig.get('displayName', '?')} -> email: {ct.get('email', 'NO EMAIL')}")
            if tgt:
                ct = contacts.get(tgt.get("id"), {})
                print(f"  target:     {tgt.get('displayName', '?')} -> email: {ct.get('email', 'NO EMAIL')}")

    print(f"\n--- twoParty calls (top 5) ---")
    for c in tp_calls[:5]:
        cl = get_call_log(c)
        print(f"\n  startTime:  {cl.get('startTime')}")
        print(f"  callState:  {cl.get('callState')}")
        orig = cl.get("originatorParticipant", {})
        tgt = cl.get("targetParticipant", {})
        if orig:
            ct = contacts.get(orig.get("id"), {})
            print(f"  originator: {orig.get('displayName', '?')} -> email: {ct.get('email', 'NO EMAIL')}")
        if tgt:
            ct = contacts.get(tgt.get("id"), {})
            print(f"  target:     {tgt.get('displayName', '?')} -> email: {ct.get('email', 'NO EMAIL')}")

    print(f"\n--- meetings (top 10) ---")
    for m in meetings[:10]:
        tp = m.get("threadProperties", {}).get("meeting", {})
        if isinstance(tp, str):
            tp = json.loads(tp)
        print(f"\n  subject:   {tp.get('subject', 'N/A')}")
        print(f"  startTime: {tp.get('startTime')}")
        print(f"  endTime:   {tp.get('endTime')}")
        members = m.get("members") or []
        print(f"  members ({len(members)}):")
        for mem in members[:20]:
            mid = mem.get("id", str(mem))
            ct = contacts.get(mid, {})
            print(f"    {mid}")
            print(f"      displayName: {ct.get('displayName', '?')}")
            print(f"      email:       {ct.get('email', 'NO EMAIL')}")

    # meeting と call のマッチング試行（threadId で紐づく場合）
    print(f"\n--- meeting/call マッチング分析 ---")
    call_threads = {}
    for c in mp_calls:
        cl = get_call_log(c)
        tid = cl.get("threadId")
        if tid:
            call_threads.setdefault(tid, []).append(cl)

    meeting_threads = {}
    for m in meetings:
        mid = m.get("id", "")
        meeting_threads[mid] = m

    matched = 0
    for tid, cls in call_threads.items():
        if tid in meeting_threads:
            matched += 1
            m = meeting_threads[tid]
            tp = m.get("threadProperties", {}).get("meeting", {})
            if isinstance(tp, str):
                tp = json.loads(tp)
            cl = cls[0]
            m_members = set(mem.get("id") for mem in (m.get("members") or []))
            c_parts = set()
            plist = cl.get("participantList") or cl.get("participants") or []
            for p in plist:
                c_parts.add(p.get("id", p) if isinstance(p, dict) else p)

            if matched <= 5:
                print(f"\n  会議: {tp.get('subject', 'N/A')}")
                print(f"    meeting members:     {len(m_members)}")
                print(f"    call participants:   {len(c_parts)}")
                only_meeting = m_members - c_parts
                only_call = c_parts - m_members
                if only_meeting:
                    print(f"    meetingのみ(招待のみ?): {len(only_meeting)}")
                    for mid in list(only_meeting)[:5]:
                        ct = contacts.get(mid, {})
                        print(f"      {ct.get('displayName', mid)}")
                if only_call:
                    print(f"    callのみ(外部参加?):   {len(only_call)}")
                    for cid in list(only_call)[:5]:
                        ct = contacts.get(cid, {})
                        print(f"      {ct.get('displayName', cid)}")

    print(f"\n  threadIdでマッチした会議数: {matched} / multiParty calls: {len(mp_calls)}")

    # 結論
    print(f"\n=== 結論 ===")
    if mp_calls:
        has_participant_data = any(
            (get_call_log(c).get("participantList") is not None and get_call_log(c)["participantList"] is not None)
            or (get_call_log(c).get("participants") is not None and get_call_log(c)["participants"] is not None)
            for c in mp_calls
        )
        if has_participant_data:
            print("  [OK] multiParty call に participantList データあり → call ベースのマッチング可能")
        else:
            print("  [NG] multiParty call の participantList は全て null → call ベースのマッチング不可")
            print("       meeting の members（招待者全員）を使う方式を検討")
    else:
        print("  [NG] multiParty call レコードが存在しない → call ベースのマッチング不可")

    if email_rate >= 80:
        print(f"  [OK] email 充填率 {email_rate:.1f}% → email マッチング実用的")
    elif email_rate >= 50:
        print(f"  [WARN] email 充填率 {email_rate:.1f}% → displayName フォールバック推奨")
    else:
        print(f"  [NG] email 充填率 {email_rate:.1f}% → displayName ベースを主軸に検討")


if __name__ == "__main__":
    main()
