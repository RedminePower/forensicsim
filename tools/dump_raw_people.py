"""
refs #2515 Phase 0: raw people レコードのフィールド構造を確認する

parser が出力した contact には mri=email のみで UUID がないため、
元の IndexedDB の people レコードにどのフィールドがあるかを確認する。

使い方:
  python dump_raw_people.py -f "%LOCALAPPDATA%\Packages\MSTeams_8wekyb3d8bbwe\LocalCache\Microsoft\MSTeams\EBWebView\Default\IndexedDB\https_teams.microsoft.com_0.indexeddb.leveldb"
"""
import sys
import os
import re

# forensicsim の src を参照可能にする
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from forensicsim.backend import parse_db
from pathlib import Path


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--filepath", required=True)
    args = parser.parse_args()

    db_path = Path(args.filepath)
    # .leveldb と同階層の .blob フォルダを自動検出
    blob_path = Path(str(db_path).replace(".leveldb", ".blob"))
    if not blob_path.exists():
        blob_path = None
    print(f"Opening: {db_path}")
    print(f"Blob path: {blob_path}\n")

    raw_records = parse_db(db_path, blobpath=blob_path, filter_db_results=True)

    # people store のレコードのみ抽出
    people_records = [r for r in raw_records if r.get("store") == "people"]
    print(f"\n=== people store レコード: {len(people_records)} 件 ===\n")

    if not people_records:
        print("people レコードが見つかりません。")
        return

    # 最初の5件の value のキーとサンプル値を出力
    print("--- raw people レコード value のキー（最初の5件）---\n")
    for i, rec in enumerate(people_records[:5]):
        value = rec.get("value", {})
        if isinstance(value, dict):
            print(f"record {i+1}: keys ({len(value.keys())}個) = {list(value.keys())[:40]}")
            # UUID 候補のフィールドを探す
            for key in ["mri", "objectId", "id", "userId", "aadObjectId",
                         "Id", "ObjectId", "UserId", "AadObjectId",
                         "email", "Email", "EmailAddresses", "emailAddresses",
                         "displayName", "DisplayName", "userPrincipalName",
                         "UserPrincipalName", "sipAddress", "SipAddress",
                         "GivenName", "givenName", "Surname", "surname"]:
                val = value.get(key)
                if val is not None:
                    val_str = str(val)[:150]
                    print(f"  {key}: {val_str}")
            print()

    # 全 people レコードの value のユニークキーを集計
    all_keys = set()
    for rec in people_records:
        value = rec.get("value", {})
        if isinstance(value, dict):
            all_keys.update(value.keys())

    print(f"--- 全 people レコードの value ユニークキー ({len(all_keys)} 個) ---")
    for k in sorted(all_keys):
        print(f"  {k}")
    print()

    # UUID っぽい値を持つフィールドを探す
    print("--- UUID を含むフィールド ---\n")
    uuid_pattern = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
    uuid_fields = {}
    for rec in people_records[:100]:
        value = rec.get("value", {})
        if isinstance(value, dict):
            for k, v in value.items():
                if k in uuid_fields:
                    continue
                v_str = str(v)
                match = uuid_pattern.search(v_str)
                if match:
                    uuid_fields[k] = v_str[:150]

    if uuid_fields:
        for k, sample in sorted(uuid_fields.items()):
            print(f"  {k}: {sample}")
    else:
        print("  UUID を含むフィールドは見つかりませんでした。")
    print()

    # 最初の1件の全フィールドダンプ
    print("--- record 1 の全フィールドダンプ ---\n")
    value = people_records[0].get("value", {})
    if isinstance(value, dict):
        for k, v in sorted(value.items()):
            v_str = str(v)[:200]
            print(f"  {k}: {v_str}")


if __name__ == "__main__":
    main()
