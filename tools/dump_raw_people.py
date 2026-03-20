"""
refs #2515 Phase 0: raw people レコードのフィールド構造を確認する

parser が出力した contact には mri=email のみで UUID がないため、
元の IndexedDB の people レコードにどのフィールドがあるかを確認する。

使い方:
  python dump_raw_people.py -f "%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\EBWebView\Default\IndexedDB\https_teams.microsoft.com_0.indexeddb.leveldb"
"""
import sys
import os
import json

# forensicsim の src を参照可能にする
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from forensicsim.backend import open_indexeddb


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--filepath", required=True)
    args = parser.parse_args()

    db_path = args.filepath
    print(f"Opening: {db_path}\n")

    people_records = []
    for record in open_indexeddb(db_path):
        store_name = record.get("store", "")
        if "people" in store_name.lower():
            people_records.append(record)

    print(f"=== people store レコード: {len(people_records)} 件 ===\n")

    if not people_records:
        print("people レコードが見つかりません。")
        print("利用可能な store 名を確認します...")
        stores = set()
        for record in open_indexeddb(db_path):
            stores.add(record.get("store", "unknown"))
        for s in sorted(stores):
            print(f"  {s}")
        return

    # 最初の5件の raw レコードのキーとサンプル値を出力
    print("--- raw people レコードのキー（最初の5件）---\n")
    for i, rec in enumerate(people_records[:5]):
        value = rec.get("value", rec)
        if isinstance(value, dict):
            print(f"record {i+1}: keys = {list(value.keys())[:30]}")
            # UUID 候補のフィールドを探す
            for key in ["mri", "objectId", "id", "userId", "aadObjectId",
                         "Id", "ObjectId", "UserId", "AadObjectId",
                         "email", "Email", "EmailAddresses", "emailAddresses",
                         "displayName", "DisplayName", "userPrincipalName"]:
                val = value.get(key)
                if val is not None:
                    val_str = str(val)[:100]
                    print(f"  {key}: {val_str}")
            print()

    # 全 people レコードのユニークキーを集計
    all_keys = set()
    for rec in people_records:
        value = rec.get("value", rec)
        if isinstance(value, dict):
            all_keys.update(value.keys())

    print(f"--- 全 people レコードのユニークキー ({len(all_keys)} 個) ---")
    for k in sorted(all_keys):
        print(f"  {k}")
    print()

    # UUID っぽいフィールド（36文字でハイフン4つ）を持つキーを探す
    print("--- UUID を含む可能性のあるフィールド ---\n")
    import re
    uuid_pattern = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
    uuid_fields = {}
    for rec in people_records[:100]:
        value = rec.get("value", rec)
        if isinstance(value, dict):
            for k, v in value.items():
                v_str = str(v)
                if uuid_pattern.search(v_str):
                    if k not in uuid_fields:
                        uuid_fields[k] = v_str[:100]

    if uuid_fields:
        for k, sample in uuid_fields.items():
            print(f"  {k}: {sample}")
    else:
        print("  UUID を含むフィールドは見つかりませんでした。")
    print()

    # 最初の1件の全フィールドをダンプ
    print("--- record 1 の全フィールドダンプ ---\n")
    value = people_records[0].get("value", people_records[0])
    if isinstance(value, dict):
        for k, v in value.items():
            v_str = str(v)[:200]
            print(f"  {k}: {v_str}")


if __name__ == "__main__":
    main()
