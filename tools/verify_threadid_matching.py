"""
Phase 0.5: meeting ↔ call の threadId 紐付け検証スクリプト

ms_teams_parser.exe の出力 JSON（パース済み）または
dump_leveldb.py の出力 JSON（生データ）に対して実行する。

確認ポイント:
1. multiParty call の callLog.threadId フィールドは存在するか？
2. meeting の id と call の threadId が一致するペアはあるか？
3. 一致するペアで、members（招待者）と participantList（実参加者）に差分はあるか？

使い方:
    python verify_threadid_matching.py -f <parsed_output.json>
    python verify_threadid_matching.py -f <raw_dump.json> --raw
"""

import argparse
import io
import json
import sys
from collections import defaultdict
from pathlib import Path

# Windows cp932 対策: stdout を UTF-8 に設定
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def extract_from_parsed(data: list[dict]) -> tuple[list[dict], list[dict]]:
    """パース済み JSON（ms_teams_parser.exe 出力）からcall/meetingを抽出"""
    calls = []
    meetings = []

    for record in data:
        rt = record.get("record_type", "")
        if rt == "call":
            call_log = record.get("properties", {}).get("call-log", {})
            if isinstance(call_log, str):
                call_log = json.loads(call_log)
            calls.append({
                "call_log": call_log,
                "conversationId": record.get("conversationId", ""),
                "composetime": record.get("composetime", ""),
                "creator": record.get("creator", ""),
            })
        elif rt == "meeting":
            meetings.append({
                "id": record.get("id", ""),
                "members": record.get("members", []),
                "threadProperties": record.get("threadProperties", {}),
            })

    return calls, meetings


def extract_from_raw(data: list[dict]) -> tuple[list[dict], list[dict]]:
    """生データ JSON（dump_leveldb.py 出力）からcall/meetingを抽出"""
    calls = []
    meetings = []

    for record in data:
        store = record.get("store", "")
        value = record.get("value", {})
        if not isinstance(value, dict):
            continue

        if store == "conversations":
            tp = value.get("threadProperties", {})
            if isinstance(tp, str):
                try:
                    tp = json.loads(tp)
                except json.JSONDecodeError:
                    tp = {}
            if isinstance(tp, dict) and tp.get("threadType") == "meeting":
                meetings.append({
                    "id": value.get("id", ""),
                    "members": value.get("members", []),
                    "threadProperties": tp,
                })

        elif store == "replychains":
            # v1: messages, v2: messageMap
            msg_dict = value.get("messages", {}) or value.get("messageMap", {})
            if not isinstance(msg_dict, dict):
                continue
            for _key, msg in msg_dict.items():
                if not isinstance(msg, dict):
                    continue
                props = msg.get("properties", {})
                if isinstance(props, str):
                    try:
                        props = json.loads(props)
                    except json.JSONDecodeError:
                        continue
                if not isinstance(props, dict):
                    continue
                if "call-log" in props:
                    call_log = props["call-log"]
                    if isinstance(call_log, str):
                        call_log = json.loads(call_log)
                    calls.append({
                        "call_log": call_log,
                        "conversationId": msg.get("conversationId",
                                                   msg.get("conversationid", "")),
                        "composetime": msg.get("composetime", ""),
                        "creator": msg.get("creator", ""),
                    })

    return calls, meetings


def analyze(calls: list[dict], meetings: list[dict]) -> None:
    """紐付け分析を実行"""
    print("=" * 70)
    print("Phase 0.5: meeting ↔ call threadId 紐付け検証")
    print("=" * 70)

    # --- 基本統計 ---
    print(f"\n■ 基本統計")
    print(f"  call レコード数:    {len(calls)}")
    print(f"  meeting レコード数: {len(meetings)}")

    # call の callType 別集計
    call_types = defaultdict(int)
    for c in calls:
        ct = c["call_log"].get("callType", "unknown")
        call_types[ct] += 1
    print(f"\n  callType 別:")
    for ct, count in sorted(call_types.items()):
        print(f"    {ct}: {count}")

    # --- 確認ポイント 1: multiParty call の threadId ---
    multi_party = [c for c in calls if c["call_log"].get("callType") in
                   ("groupCall", "multiParty")]
    print(f"\n■ 確認ポイント 1: multiParty/groupCall の threadId")
    print(f"  multiParty/groupCall 件数: {len(multi_party)}")

    thread_id_present = 0
    thread_id_none = 0
    participant_list_present = 0
    participant_list_none = 0

    for c in multi_party:
        cl = c["call_log"]
        tid = cl.get("threadId")
        pl = cl.get("participantList")
        if tid and tid != "None":
            thread_id_present += 1
        else:
            thread_id_none += 1
        if pl and pl != "None" and len(pl) > 0:
            participant_list_present += 1
        else:
            participant_list_none += 1

    print(f"  threadId あり:        {thread_id_present}")
    print(f"  threadId なし/null:   {thread_id_none}")
    print(f"  participantList あり: {participant_list_present}")
    print(f"  participantList なし: {participant_list_none}")

    # twoParty も参考情報として
    two_party = [c for c in calls if c["call_log"].get("callType") in
                 ("twoParty",)]
    tp_with_tid = sum(1 for c in two_party
                      if c["call_log"].get("threadId") not in (None, "None", ""))
    print(f"\n  (参考) twoParty: {len(two_party)} 件, threadId あり: {tp_with_tid}")

    # --- 確認ポイント 2: meeting.id と call.threadId の一致 ---
    print(f"\n■ 確認ポイント 2: meeting.id ↔ call.threadId 紐付け")

    meeting_by_id = {}
    for m in meetings:
        mid = m.get("id", "")
        if mid:
            meeting_by_id[mid] = m

    matched_pairs = []
    unmatched_calls = []
    for c in multi_party:
        tid = c["call_log"].get("threadId")
        if tid and tid in meeting_by_id:
            matched_pairs.append((c, meeting_by_id[tid]))
        elif tid and tid not in (None, "None", ""):
            unmatched_calls.append(c)

    print(f"  meeting ID 数（ユニーク）:     {len(meeting_by_id)}")
    print(f"  threadId で紐付け成功:         {len(matched_pairs)}")
    print(f"  threadId あるが meeting 不一致: {len(unmatched_calls)}")

    # --- フォーマット比較: threadId vs meeting.id サンプル ---
    if unmatched_calls or (thread_id_present > 0 and len(matched_pairs) == 0):
        print(f"\n■ フォーマット比較: call.threadId vs meeting.id")

        # call.threadId サンプル（ユニーク値、最大10件）
        unique_tids = sorted(set(
            c["call_log"].get("threadId", "")
            for c in multi_party
            if c["call_log"].get("threadId") not in (None, "None", "")
        ))
        print(f"\n  call.threadId サンプル（{len(unique_tids)} 種類中、最大10件）:")
        for tid in unique_tids[:10]:
            print(f"    {tid}")

        # meeting.id サンプル（最大10件）
        unique_mids = sorted(meeting_by_id.keys())
        print(f"\n  meeting.id サンプル（{len(unique_mids)} 種類中、最大10件）:")
        for mid in unique_mids[:10]:
            print(f"    {mid}")

        # 部分一致の試行
        print(f"\n  部分一致の試行:")
        partial_match_count = 0
        partial_examples = []
        for c in multi_party:
            tid = c["call_log"].get("threadId", "")
            if not tid or tid in (None, "None", ""):
                continue
            for mid in meeting_by_id:
                if tid in mid or mid in tid:
                    partial_match_count += 1
                    if len(partial_examples) < 3:
                        partial_examples.append((tid, mid))
                    break
        print(f"    部分一致（substring）: {partial_match_count} 件")
        for tid, mid in partial_examples:
            print(f"      threadId: {tid}")
            print(f"      meeting:  {mid}")
            print()

        # UUID 抽出による一致の試行
        import re
        uuid_pattern = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.IGNORECASE)

        tid_uuids = {}  # uuid -> threadId
        for c in multi_party:
            tid = c["call_log"].get("threadId", "")
            if not tid or tid in (None, "None", ""):
                continue
            for m in uuid_pattern.findall(tid):
                tid_uuids[m.lower()] = tid

        mid_uuids = {}  # uuid -> meeting.id
        for mid in meeting_by_id:
            for m in uuid_pattern.findall(mid):
                mid_uuids[m.lower()] = mid

        uuid_matches = set(tid_uuids.keys()) & set(mid_uuids.keys())
        print(f"    UUID 抽出による一致: {len(uuid_matches)} 件")
        print(f"    threadId 内の UUID 数: {len(tid_uuids)}")
        print(f"    meeting.id 内の UUID 数: {len(mid_uuids)}")
        for uuid_val in list(uuid_matches)[:3]:
            print(f"      UUID:     {uuid_val}")
            print(f"      threadId: {tid_uuids[uuid_val]}")
            print(f"      meeting:  {mid_uuids[uuid_val]}")
            print()

        # Base64 デコードの試行（meeting.id の meeting_XXXX 部分）
        import base64
        mid_decoded = {}  # decoded -> meeting.id
        for mid in meeting_by_id:
            b64_match = re.search(r'meeting_([A-Za-z0-9+/=_-]+)@', mid)
            if b64_match:
                b64_str = b64_match.group(1)
                # URL-safe base64 → standard base64
                b64_str_std = b64_str.replace('-', '+').replace('_', '/')
                # パディング補完
                b64_str_std += '=' * (4 - len(b64_str_std) % 4) if len(b64_str_std) % 4 else ''
                try:
                    decoded = base64.b64decode(b64_str_std).decode('utf-8', errors='replace')
                    mid_decoded[mid] = decoded
                except Exception:
                    pass

        if mid_decoded:
            print(f"    meeting.id の Base64 デコード（最大5件）:")
            for mid, decoded in list(mid_decoded.items())[:5]:
                print(f"      {mid[:60]}...")
                print(f"      -> decoded: {decoded}")

    if matched_pairs:
        print(f"\n  紐付けペア一覧:")
        for i, (call, meeting) in enumerate(matched_pairs):
            cl = call["call_log"]
            tp = meeting.get("threadProperties", {})
            mtg_info = tp.get("meeting", {}) if isinstance(tp, dict) else {}
            subject = mtg_info.get("subject", tp.get("topic", "N/A"))
            print(f"\n  [{i+1}] {subject}")
            print(f"      meeting.id:     {meeting['id'][:60]}...")
            print(f"      call.threadId:  {cl.get('threadId', '')[:60]}...")
            print(f"      call.startTime: {cl.get('startTime', 'N/A')}")

    # --- 確認ポイント 3: members vs participantList 差分 ---
    print(f"\n■ 確認ポイント 3: members（招待者）vs participantList（実参加者）差分")

    if not matched_pairs:
        print("  紐付けペアがないため差分比較不可")
    else:
        for i, (call, meeting) in enumerate(matched_pairs):
            cl = call["call_log"]
            tp = meeting.get("threadProperties", {})
            mtg_info = tp.get("meeting", {}) if isinstance(tp, dict) else {}
            subject = mtg_info.get("subject", tp.get("topic", "N/A"))

            # meeting members（招待者）
            members = meeting.get("members", []) or []
            member_ids = set()
            for m in members:
                mid = m.get("id", "") if isinstance(m, dict) else str(m)
                if mid:
                    member_ids.add(mid)

            # call participantList（実参加者）
            pl = cl.get("participantList", []) or []
            participant_ids = set()
            for p in pl:
                if isinstance(p, dict):
                    pid = p.get("id", p.get("mri", ""))
                elif isinstance(p, str):
                    pid = p
                else:
                    continue
                if pid:
                    participant_ids.add(pid)

            only_invited = member_ids - participant_ids
            only_actual = participant_ids - member_ids
            both = member_ids & participant_ids

            print(f"\n  [{i+1}] {subject}")
            print(f"      招待者 (members):       {len(member_ids)}")
            print(f"      実参加者 (participants): {len(participant_ids)}")
            print(f"      両方に存在:             {len(both)}")
            print(f"      招待のみ（不参加）:     {len(only_invited)}")
            print(f"      参加のみ（招待外）:     {len(only_actual)}")

            if only_invited:
                print(f"      不参加者: {list(only_invited)[:5]}{'...' if len(only_invited) > 5 else ''}")
            if only_actual:
                print(f"      招待外参加者: {list(only_actual)[:5]}{'...' if len(only_actual) > 5 else ''}")

    # --- 結論 ---
    print(f"\n{'=' * 70}")
    print("■ 結論")
    if thread_id_present > 0 and len(matched_pairs) > 0:
        match_rate = len(matched_pairs) / thread_id_present * 100
        print(f"  → 紐付け可能（マッチ率: {match_rate:.0f}%）")
        print(f"  → TeamsMeeting でも実参加者を特定可能")
        print(f"  → call + meeting 両方を自動共有対象にできる")
    elif thread_id_present > 0:
        print(f"  → threadId は存在するが meeting との紐付け不可")
        print(f"  → 別の紐付けキー（時刻、subject等）の検討が必要")
    elif len(multi_party) == 0:
        print(f"  → multiParty/groupCall が存在しない（テストデータ不足）")
        print(f"  → 実データ（会社PC）で再実行してください")
    else:
        print(f"  → 紐付け不可（threadId が全て null）")
        print(f"  → TeamsCall のみ自動共有対象。TeamsMeeting は従来通り手動")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Phase 0.5: meeting ↔ call の threadId 紐付け検証")
    parser.add_argument("-f", "--filepath", required=True,
                        help="ms_teams_parser.exe 出力 JSON のパス")
    parser.add_argument("--raw", action="store_true",
                        help="dump_leveldb.py の生データ形式の場合に指定")
    args = parser.parse_args()

    filepath = Path(args.filepath)
    if not filepath.exists():
        print(f"エラー: ファイルが見つかりません: {filepath}", file=sys.stderr)
        sys.exit(1)

    print(f"読み込み中: {filepath}")
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print(f"エラー: JSON のルートがリストではありません: {type(data)}", file=sys.stderr)
        sys.exit(1)

    if args.raw:
        calls, meetings = extract_from_raw(data)
    else:
        calls, meetings = extract_from_parsed(data)

    analyze(calls, meetings)


if __name__ == "__main__":
    main()
