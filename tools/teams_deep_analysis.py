"""
Teams データ詳細分析スクリプト
contact 以外の場所に参加者名・メールが含まれていないか調査する。

使い方:
  python teams_deep_analysis.py %TEMP%\teams_output.json
"""

import json
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


def find_emails_in_obj(obj, path=""):
    """オブジェクト内から email っぽい文字列を再帰的に探す"""
    results = []
    if isinstance(obj, str):
        if "@" in obj and "." in obj and "orgid" not in obj:
            results.append((path, obj))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            results.extend(find_emails_in_obj(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:10]):  # 最大10件
            results.extend(find_emails_in_obj(v, f"{path}[{i}]"))
    return results


def find_display_names_in_obj(obj, path=""):
    """displayName, name, userName 等のキーを再帰的に探す"""
    results = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(n in k.lower() for n in ["name", "display", "user", "organizer", "creator"]):
                if isinstance(v, str) and v and len(v) > 1:
                    results.append((f"{path}.{k}", v))
            results.extend(find_display_names_in_obj(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:10]):
            results.extend(find_display_names_in_obj(v, f"{path}[{i}]"))
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python teams_deep_analysis.py <teams_output.json>")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)

    record_types = {}
    for r in data:
        rt = r.get("record_type", "unknown")
        record_types[rt] = record_types.get(rt, 0) + 1

    print("=" * 60)
    print("1. レコードタイプ別件数")
    print("=" * 60)
    for rt, count in sorted(record_types.items(), key=lambda x: -x[1]):
        print(f"  {rt}: {count}")

    # =========================================
    print("\n" + "=" * 60)
    print("2. contact レコードのキー構造（最初の3件）")
    print("=" * 60)
    contacts = [r for r in data if r.get("record_type") == "contact"]
    for i, c in enumerate(contacts[:3]):
        print(f"\n  --- contact [{i}] ---")
        print(f"  トップレベルキー: {list(c.keys())}")
        for k, v in c.items():
            if isinstance(v, dict):
                print(f"  {k}: (dict) keys={list(v.keys())[:15]}")
            elif isinstance(v, list):
                print(f"  {k}: (list) len={len(v)}")
            elif isinstance(v, str) and len(v) > 100:
                print(f"  {k}: '{v[:100]}...'")
            else:
                print(f"  {k}: {v}")

    # =========================================
    print("\n" + "=" * 60)
    print("3. contact に email/displayName がある件数")
    print("=" * 60)
    has_email = sum(1 for c in contacts if c.get("email"))
    has_display = sum(1 for c in contacts if c.get("displayName"))
    has_upn = sum(1 for c in contacts if c.get("userPrincipalName") or c.get("user_principal_name"))
    # 他のキーで名前っぽいものを探す
    name_keys = set()
    for c in contacts[:50]:
        for k in c.keys():
            if "name" in k.lower() or "mail" in k.lower() or "email" in k.lower():
                if c[k]:
                    name_keys.add(k)
    print(f"  email あり: {has_email}/{len(contacts)}")
    print(f"  displayName あり: {has_display}/{len(contacts)}")
    print(f"  userPrincipalName あり: {has_upn}/{len(contacts)}")
    print(f"  名前/メール関連の非空キー: {name_keys if name_keys else 'なし'}")

    # =========================================
    print("\n" + "=" * 60)
    print("4. meeting レコードの詳細構造（最初の3件）")
    print("=" * 60)
    meetings = [r for r in data if r.get("record_type") == "meeting"]
    for i, m in enumerate(meetings[:3]):
        print(f"\n  --- meeting [{i}] ---")
        print(f"  トップレベルキー: {list(m.keys())}")

        # threadProperties の中身
        tp = m.get("threadProperties", {})
        print(f"  threadProperties キー: {list(tp.keys()) if isinstance(tp, dict) else type(tp)}")

        meeting_info = tp.get("meeting", {})
        if isinstance(meeting_info, str):
            try:
                meeting_info = json.loads(meeting_info)
            except:
                pass
        if isinstance(meeting_info, dict):
            print(f"  threadProperties.meeting キー: {list(meeting_info.keys())}")
            for k, v in meeting_info.items():
                if isinstance(v, str) and len(v) > 200:
                    print(f"    {k}: '{v[:200]}...'")
                else:
                    print(f"    {k}: {v}")

        # members の詳細
        members = m.get("members", [])
        print(f"  members: {len(members)}件")
        for j, mem in enumerate(members[:3]):
            print(f"    [{j}] {mem}")

        # meeting 内のメールアドレス検索
        emails = find_emails_in_obj(m, "meeting")
        if emails:
            print(f"  発見されたメールアドレス:")
            for path, email in emails:
                print(f"    {path} = {email}")

        # meeting 内の名前検索
        names = find_display_names_in_obj(m, "meeting")
        if names:
            print(f"  発見された名前情報:")
            for path, name in names[:10]:
                print(f"    {path} = {name}")

    # =========================================
    print("\n" + "=" * 60)
    print("5. meeting の organizerId 分析")
    print("=" * 60)
    organizer_ids = set()
    for m in meetings:
        tp = m.get("threadProperties", {})
        mi = tp.get("meeting", {})
        if isinstance(mi, str):
            try:
                mi = json.loads(mi)
            except:
                mi = {}
        if isinstance(mi, dict):
            oid = mi.get("organizerId")
            if oid:
                organizer_ids.add(oid)
    print(f"  ユニーク organizerId 数: {len(organizer_ids)}")
    for oid in list(organizer_ids)[:5]:
        print(f"    {oid}")

    # =========================================
    print("\n" + "=" * 60)
    print("6. 全データからメールアドレスを検索（サンプル50件）")
    print("=" * 60)
    all_emails = set()
    for r in data[:200]:
        for path, email in find_emails_in_obj(r, r.get("record_type", "?")):
            all_emails.add((path, email))
    if all_emails:
        print(f"  発見されたメールアドレス: {len(all_emails)}件")
        for path, email in list(all_emails)[:20]:
            print(f"    {path} = {email}")
    else:
        print("  メールアドレスは見つかりませんでした")

    # =========================================
    print("\n" + "=" * 60)
    print("7. message レコードの分析（会議チャットに参加者情報がないか）")
    print("=" * 60)
    messages = [r for r in data if r.get("record_type") == "message"]
    print(f"  message レコード数: {len(messages)}")
    if messages:
        print(f"\n  --- message[0] のキー構造 ---")
        m0 = messages[0]
        print(f"  トップレベルキー: {list(m0.keys())}")
        # imdisplayname や creator 等を探す
        for k in ["imdisplayname", "creator", "from", "sender", "displayName",
                   "im_display_name", "creator_display_name"]:
            if k in m0:
                print(f"  {k}: {m0[k]}")

        # from フィールドの分析
        sender_names = set()
        for msg in messages[:100]:
            for k in ["imdisplayname", "im_display_name", "creator_display_name"]:
                v = msg.get(k)
                if v and isinstance(v, str) and len(v) > 1:
                    sender_names.add(v)
        if sender_names:
            print(f"\n  メッセージ送信者名（imdisplayname等）: {len(sender_names)}件")
            for name in list(sender_names)[:20]:
                print(f"    {name}")

        # message から creator(mri) と名前の対応を構築
        mri_to_name = {}
        for msg in messages:
            creator = msg.get("creator")
            name = msg.get("imdisplayname") or msg.get("im_display_name") or msg.get("creator_display_name")
            if creator and name and isinstance(name, str) and len(name) > 1:
                mri_to_name[creator] = name
        if mri_to_name:
            print(f"\n  message から構築できた MRI→名前マッピング: {len(mri_to_name)}件")
            for mri, name in list(mri_to_name.items())[:20]:
                print(f"    {mri} -> {name}")

    # =========================================
    print("\n" + "=" * 60)
    print("8. meeting members を message の MRI→名前で解決")
    print("=" * 60)
    if mri_to_name and meetings:
        resolved = 0
        total_members = 0
        for m in meetings[:10]:
            tp = m.get("threadProperties", {})
            mi = tp.get("meeting", {})
            if isinstance(mi, str):
                try:
                    mi = json.loads(mi)
                except:
                    mi = {}
            subject = mi.get("subject", "?") if isinstance(mi, dict) else "?"
            members = m.get("members", [])
            total_members += len(members)
            resolved_members = []
            for mem in members:
                mid = mem.get("id", str(mem)) if isinstance(mem, dict) else str(mem)
                name = mri_to_name.get(mid)
                if name:
                    resolved += 1
                    resolved_members.append(name)
            print(f"\n  会議: {subject}")
            print(f"    members: {len(members)}人, 名前解決: {len(resolved_members)}人")
            if resolved_members:
                for name in resolved_members:
                    print(f"      {name}")
        print(f"\n  合計: {total_members}人中 {resolved}人の名前を解決")
    else:
        print("  MRI→名前マッピングが構築できなかったため、解決不可")

    # =========================================
    print("\n" + "=" * 60)
    print("9. 結論")
    print("=" * 60)
    if 'mri_to_name' in dir() and mri_to_name:
        print(f"  [発見] message レコードの imdisplayname から {len(mri_to_name)}件の")
        print(f"         MRI→名前マッピングを構築可能")
        print(f"  → displayName ベースで Redmine ユーザーとマッチングできる可能性あり")
        print(f"  → ただし email は取得不可のため、名前の完全一致が必要")
    else:
        print("  [NG] 参加者を特定する手段が見つかりませんでした")
        print("  → Microsoft Graph API の利用を検討してください")


if __name__ == "__main__":
    main()
