"""
Teams call レコード詳細分析スクリプト
call レコードの構造と参加者情報を詳しく調査する。

使い方:
  python teams_call_analysis.py %TEMP%\teams_output.json
"""

import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def main():
    if len(sys.argv) < 2:
        print("Usage: python teams_call_analysis.py <teams_output.json>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)

    calls = [r for r in data if r.get("record_type") == "call"]
    meetings = [r for r in data if r.get("record_type") == "meeting"]
    messages = [r for r in data if r.get("record_type") == "message"]

    print("=" * 60)
    print(f"call レコード数: {len(calls)}")
    print(f"meeting レコード数: {len(meetings)}")
    print(f"message レコード数: {len(messages)}")
    print("=" * 60)

    if not calls:
        print("[NG] call レコードが存在しません")
        pause_exit()
        return

    # =========================================
    print("\n" + "=" * 60)
    print("1. call レコードのキー構造（最初の3件）")
    print("=" * 60)
    for i, c in enumerate(calls[:3]):
        print(f"\n  --- call [{i}] ---")
        print(f"  トップレベルキー: {list(c.keys())}")
        props = c.get("properties", {})
        print(f"  properties のキー: {list(props.keys())}")

        # call-log の中身を詳細表示
        # キー名は "call-log" (パーサー出力) と "callLog" (TeamsService.cs変換後) 両方チェック
        call_log = props.get("call-log") or props.get("callLog")
        if call_log:
            if isinstance(call_log, str):
                try:
                    call_log = json.loads(call_log)
                except:
                    pass
            if isinstance(call_log, dict):
                print(f"  call-log のキー: {list(call_log.keys())}")
                for k, v in call_log.items():
                    if isinstance(v, (dict, list)):
                        if isinstance(v, list):
                            print(f"    {k}: (list) {len(v)}件")
                            for j, item in enumerate(v[:3]):
                                print(f"      [{j}] {item}")
                        else:
                            print(f"    {k}: {json.dumps(v, ensure_ascii=False, default=str)[:200]}")
                    else:
                        print(f"    {k}: {v}")
            else:
                print(f"  call-log (type={type(call_log).__name__}): {str(call_log)[:300]}")
        else:
            print("  [!] call-log キーが見つかりません")
            print(f"  properties の中身: {json.dumps(props, ensure_ascii=False, default=str)[:500]}")

    # =========================================
    print("\n" + "=" * 60)
    print("2. callType 別の内訳")
    print("=" * 60)
    call_types = {}
    for c in calls:
        props = c.get("properties", {})
        cl = props.get("call-log") or props.get("callLog") or {}
        if isinstance(cl, str):
            try:
                cl = json.loads(cl)
            except:
                cl = {}
        ct = cl.get("callType", "unknown") if isinstance(cl, dict) else "parse_error"
        call_types[ct] = call_types.get(ct, 0) + 1
    for ct, count in sorted(call_types.items(), key=lambda x: -x[1]):
        print(f"  {ct}: {count}")

    # =========================================
    print("\n" + "=" * 60)
    print("3. multiParty call の詳細（参加者情報）")
    print("=" * 60)
    mp_calls = []
    for c in calls:
        props = c.get("properties", {})
        cl = props.get("call-log") or props.get("callLog") or {}
        if isinstance(cl, str):
            try:
                cl = json.loads(cl)
            except:
                cl = {}
        if isinstance(cl, dict) and cl.get("callType") == "multiParty":
            mp_calls.append((c, cl))

    print(f"  multiParty call 数: {len(mp_calls)}")
    for i, (c, cl) in enumerate(mp_calls[:10]):
        print(f"\n  --- multiParty [{i}] ---")
        print(f"  startTime:  {cl.get('startTime')}")
        print(f"  endTime:    {cl.get('endTime')}")
        print(f"  callState:  {cl.get('callState')}")
        print(f"  callDirection: {cl.get('callDirection')}")

        # participantList
        plist = cl.get("participantList")
        print(f"  participantList: {plist if plist is None else f'{len(plist)}件'}")
        if plist:
            for j, p in enumerate(plist[:10]):
                print(f"    [{j}] {p}")

        # participants
        parts = cl.get("participants")
        print(f"  participants: {parts if parts is None else f'{len(parts)}件'}")
        if parts:
            for j, p in enumerate(parts[:10]):
                print(f"    [{j}] {p}")

        # originator/target
        orig = cl.get("originatorParticipant") or cl.get("originator")
        tgt = cl.get("targetParticipant") or cl.get("target")
        print(f"  originator: {orig}")
        print(f"  target:     {tgt}")

        # threadId (meeting とのマッチング用)
        tid = cl.get("threadId")
        print(f"  threadId:   {tid}")

        # その他の参加者関連キー
        for k in cl.keys():
            if any(x in k.lower() for x in ["participant", "member", "attendee", "user", "name", "email"]):
                if k not in ["participantList", "participants", "originatorParticipant", "targetParticipant"]:
                    print(f"  {k}: {cl[k]}")

    # =========================================
    print("\n" + "=" * 60)
    print("4. twoParty call の詳細（参加者情報）")
    print("=" * 60)
    tp_calls = []
    for c in calls:
        props = c.get("properties", {})
        cl = props.get("call-log") or props.get("callLog") or {}
        if isinstance(cl, str):
            try:
                cl = json.loads(cl)
            except:
                cl = {}
        if isinstance(cl, dict) and cl.get("callType") == "twoParty":
            tp_calls.append((c, cl))

    print(f"  twoParty call 数: {len(tp_calls)}")
    for i, (c, cl) in enumerate(tp_calls[:5]):
        print(f"\n  --- twoParty [{i}] ---")
        print(f"  startTime:  {cl.get('startTime')}")
        print(f"  callState:  {cl.get('callState')}")
        print(f"  callDirection: {cl.get('callDirection')}")
        orig = cl.get("originatorParticipant")
        tgt = cl.get("targetParticipant")
        print(f"  originator: {orig}")
        print(f"  target:     {tgt}")

    # =========================================
    print("\n" + "=" * 60)
    print("5. call レコードの全キー集計（どのキーに情報があるか）")
    print("=" * 60)
    all_call_log_keys = {}
    non_null_keys = {}
    for c in calls:
        props = c.get("properties", {})
        cl = props.get("call-log") or props.get("callLog") or {}
        if isinstance(cl, str):
            try:
                cl = json.loads(cl)
            except:
                cl = {}
        if isinstance(cl, dict):
            for k, v in cl.items():
                all_call_log_keys[k] = all_call_log_keys.get(k, 0) + 1
                if v is not None and v != "" and v != [] and v != {}:
                    non_null_keys[k] = non_null_keys.get(k, 0) + 1

    print(f"  {'キー':<30} {'出現回数':>8} {'非null':>8}")
    print(f"  {'-'*30} {'-'*8} {'-'*8}")
    for k in sorted(all_call_log_keys.keys()):
        total = all_call_log_keys[k]
        non_null = non_null_keys.get(k, 0)
        marker = " <-- !!!" if k in ["participantList", "participants", "displayName", "email"] and non_null > 0 else ""
        print(f"  {k:<30} {total:>8} {non_null:>8}{marker}")

    # =========================================
    print("\n" + "=" * 60)
    print("6. call の creator/conversationId から名前解決の試行")
    print("=" * 60)
    # message の中から creator と displayName 的な情報を探す
    creator_info = {}
    for msg in messages[:5000]:
        creator = msg.get("creator")
        # v2 では imdisplayname がないが、content に名前が含まれる可能性
        display = msg.get("imdisplayname") or msg.get("im_display_name")
        if creator and display:
            creator_info[creator] = display

    print(f"  message から取得できた creator→名前: {len(creator_info)}件")
    if creator_info:
        for cid, name in list(creator_info.items())[:10]:
            print(f"    {cid} -> {name}")

    # call の originator/target が message の creator と一致するか
    call_creators = set()
    for c in calls[:500]:
        props = c.get("properties", {})
        cl = props.get("call-log") or props.get("callLog") or {}
        if isinstance(cl, str):
            try:
                cl = json.loads(cl)
            except:
                cl = {}
        if isinstance(cl, dict):
            orig = cl.get("originatorParticipant", {})
            tgt = cl.get("targetParticipant", {})
            if isinstance(orig, dict) and orig.get("id"):
                call_creators.add(orig["id"])
            if isinstance(tgt, dict) and tgt.get("id"):
                call_creators.add(tgt["id"])
            if isinstance(orig, str):
                call_creators.add(orig)
            if isinstance(tgt, str):
                call_creators.add(tgt)

    print(f"\n  call の参加者 ID 数: {len(call_creators)}")
    resolved = 0
    for cid in call_creators:
        if cid in creator_info:
            resolved += 1
            print(f"    [解決] {cid} -> {creator_info[cid]}")
    print(f"\n  解決できた ID: {resolved}/{len(call_creators)}")

    # =========================================
    print("\n" + "=" * 60)
    print("7. call の displayName 直接取得")
    print("=" * 60)
    # originatorParticipant / targetParticipant に displayName が含まれるか
    names_found = 0
    for i, c in enumerate(calls[:100]):
        props = c.get("properties", {})
        cl = props.get("call-log") or props.get("callLog") or {}
        if isinstance(cl, str):
            try:
                cl = json.loads(cl)
            except:
                cl = {}
        if isinstance(cl, dict):
            orig = cl.get("originatorParticipant", {})
            tgt = cl.get("targetParticipant", {})
            orig_name = orig.get("displayName") if isinstance(orig, dict) else None
            tgt_name = tgt.get("displayName") if isinstance(tgt, dict) else None
            if orig_name or tgt_name:
                names_found += 1
                if names_found <= 10:
                    print(f"  call[{i}]: originator={orig_name}, target={tgt_name}")
    print(f"\n  displayName が含まれる call: {names_found}/100件（先頭100件中）")

    # =========================================
    print("\n" + "=" * 60)
    print("8. 結論")
    print("=" * 60)
    if len(mp_calls) > 0:
        has_plist = any(cl.get("participantList") for _, cl in mp_calls)
        if has_plist:
            print("  [OK] multiParty call の participantList にデータあり")
            print("  → call ベースのマッチングが可能")
        else:
            print("  [NG] multiParty call の participantList は全て null")
    else:
        print(f"  [INFO] multiParty call: 0件")

    if names_found > 0:
        print(f"  [OK] call の originatorParticipant/targetParticipant に displayName あり")
        print(f"  → displayName ベースで Redmine ユーザーとマッチング可能")
    else:
        print(f"  [NG] call に displayName なし")

    if creator_info:
        print(f"  [OK] message から {len(creator_info)}件の MRI→名前マッピング構築可能")
    else:
        print(f"  [NG] message からの名前解決不可")

    total_tp = len(tp_calls)
    total_mp = len(mp_calls)
    print(f"\n  call 内訳: twoParty={total_tp}, multiParty={total_mp}")
    if total_tp > 0 and total_mp == 0:
        print("  → 1対1通話のみ。会議通話レコードは meeting から取得する方式を検討")


def pause_exit():
    input("Press any key to continue . . .")


if __name__ == "__main__":
    main()
