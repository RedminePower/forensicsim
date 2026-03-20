"""
refs #2515 Phase 0: call レコードの構造を詳細に出力するスクリプト

callType が N/A だったため、v2 の call レコードにどのようなフィールドがあるかを確認する。

使い方:
  python dump_call_structure.py C:\tmp\teams_output.json
"""
import json
import sys


def main():
    if len(sys.argv) < 2:
        print("Usage: python dump_call_structure.py <teams_output.json>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)

    calls = [r for r in data if r.get("record_type") == "call"]
    print(f"=== call レコード: {len(calls)} 件 ===\n")

    if not calls:
        print("call レコードがありません。")
        return

    # 最初の5件の callLog キーを出力
    print("--- callLog のキー一覧（最初の5件）---\n")
    for i, c in enumerate(calls[:5]):
        cl = c.get("properties", {}).get("callLog", {})
        print(f"call {i+1}: callLog keys = {list(cl.keys())}")
        print(f"  callState: {cl.get('callState')}")
        print(f"  callType: {cl.get('callType')}")
        print(f"  callDirection: {cl.get('callDirection')}")
        print(f"  participantList: {cl.get('participantList')}")
        print(f"  participants: {cl.get('participants')}")
        print()

    # properties の直下キーも確認
    print("--- properties のキー一覧（最初の5件）---\n")
    for i, c in enumerate(calls[:5]):
        props = c.get("properties", {})
        print(f"call {i+1}: properties keys = {list(props.keys())}")
        print()

    # callLog 以外に参加者情報がないか、全キーをユニークに集計
    all_calllog_keys = set()
    all_props_keys = set()
    for c in calls:
        props = c.get("properties", {})
        all_props_keys.update(props.keys())
        cl = props.get("callLog", {})
        if isinstance(cl, dict):
            all_calllog_keys.update(cl.keys())

    print(f"--- 全 call レコードの callLog キー（ユニーク）---")
    print(f"  {sorted(all_calllog_keys)}\n")
    print(f"--- 全 call レコードの properties キー（ユニーク）---")
    print(f"  {sorted(all_props_keys)}\n")

    # participantList を持つ call を集計
    has_plist = [c for c in calls if c.get("properties", {}).get("callLog", {}).get("participantList")]
    has_participants = [c for c in calls if c.get("properties", {}).get("callLog", {}).get("participants")]
    print(f"--- participantList を持つ call: {len(has_plist)} 件 ---")
    print(f"--- participants を持つ call: {len(has_participants)} 件 ---\n")

    # participantList がある call の詳細（最初の5件）
    if has_plist:
        print("--- participantList がある call の詳細（最初の5件）---\n")
        contacts = {r["mri"]: r for r in data if r.get("record_type") == "contact"}
        for i, c in enumerate(has_plist[:5]):
            cl = c["properties"]["callLog"]
            print(f"call {i+1}:")
            print(f"  startTime: {cl.get('startTime')}")
            print(f"  endTime: {cl.get('endTime')}")
            print(f"  callState: {cl.get('callState')}")
            plist = cl["participantList"]
            print(f"  participantList ({len(plist)}):")
            for p in plist:
                pid = p.get("id", p) if isinstance(p, dict) else p
                print(f"    {pid}")
            print()


if __name__ == "__main__":
    main()
