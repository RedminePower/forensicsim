"""
refs #2515 Phase 0: contact と participantList の ID 照合デバッグ

contact の mri と call の participantList ID を比較し、
なぜ照合が失敗しているかを特定する。

使い方:
  python debug_contact_matching.py C:\tmp\teams_output.json
"""
import json
import sys


def get_call_log(call):
    props = call.get("properties", {})
    return props.get("call-log", props.get("callLog", {})) or {}


def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_contact_matching.py <teams_output.json>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)

    contacts = [r for r in data if r.get("record_type") == "contact"]
    calls = [r for r in data if r.get("record_type") == "call"]

    # --- contact の mri サンプル ---
    print(f"=== contacts: {len(contacts)} 件 ===\n")
    print("--- contact の mri サンプル（最初の10件）---")
    for i, c in enumerate(contacts[:10]):
        print(f"  mri: {c.get('mri')}")
        print(f"    displayName: {c.get('displayName')}")
        print(f"    email: {c.get('email')}")
    print()

    # --- contact の mri 形式を集計 ---
    mri_formats = {"UUID のみ": 0, "8:orgid:UUID": 0, "その他": 0}
    for c in contacts:
        mri = c.get("mri", "")
        if mri.startswith("8:orgid:"):
            mri_formats["8:orgid:UUID"] += 1
        elif len(mri) == 36 and mri.count("-") == 4:
            mri_formats["UUID のみ"] += 1
        else:
            mri_formats["その他"] += 1
    print("--- contact の mri 形式の集計 ---")
    for fmt, count in mri_formats.items():
        print(f"  {fmt}: {count} 件")
    print()

    # --- multiParty call の participantList ID サンプル ---
    mp_calls = [c for c in calls if get_call_log(c).get("callType") == "multiParty"]
    if mp_calls:
        cl = get_call_log(mp_calls[0])
        plist = cl.get("participantList", [])
        participants = cl.get("participants", [])

        print("--- call 1 の participantList ID ---")
        for p in plist:
            pid = p.get("id", p) if isinstance(p, dict) else p
            print(f"  participantList ID: {pid}")
        print()

        print("--- call 1 の participants ID ---")
        for p in participants:
            pid = p.get("id", p) if isinstance(p, dict) else p
            print(f"  participants ID: {pid}")
        print()

        # --- 照合テスト ---
        print("--- 照合テスト ---")
        contact_dict = {c.get("mri"): c for c in contacts}
        test_ids = []
        for p in plist:
            pid = p.get("id", p) if isinstance(p, dict) else p
            test_ids.append(pid)
        for p in participants:
            pid = p.get("id", p) if isinstance(p, dict) else p
            if pid not in test_ids:
                test_ids.append(pid)

        for pid in test_ids:
            print(f"\n  テスト ID: {pid}")

            # 完全一致
            exact = contact_dict.get(pid)
            print(f"    完全一致: {'あり' if exact else 'なし'}")

            # UUID 抽出して部分一致
            uuid = pid.split(":")[-1] if isinstance(pid, str) and ":" in pid else pid
            print(f"    抽出 UUID: {uuid}")

            partial = None
            for k, v in contact_dict.items():
                if uuid and k and uuid in k:
                    partial = v
                    break
            print(f"    UUID部分一致: {'あり' if partial else 'なし'}")

            # 逆方向: contact の mri が participant ID に含まれるか
            reverse = None
            for k, v in contact_dict.items():
                if k and k in pid:
                    reverse = v
                    break
            print(f"    逆方向一致 (mri in pid): {'あり - mri=' + k if reverse else 'なし'}")

            if partial:
                print(f"    -> {partial.get('displayName')} ({partial.get('email')})")
            elif reverse:
                print(f"    -> {reverse.get('displayName')} ({reverse.get('email')})")


if __name__ == "__main__":
    main()
