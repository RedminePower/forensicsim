import json
import logging
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Optional, Union

from bs4 import BeautifulSoup, MarkupResemblesLocatorWarning
from dataclasses_json import (
    DataClassJsonMixin,
    LetterCase,
    Undefined,
    config,
    dataclass_json,
)

from forensicsim.backend import parse_db, write_results_to_json

# Suppress Beautiful Soup warnings
warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)


def strip_html_tags(value: str) -> str:
    # Get the text of any embedded html, such as divs, a href links
    soup = BeautifulSoup(value, features="html.parser")
    return soup.get_text()


def decode_dict(properties: Union[bytes, str, dict]) -> dict[str, Any]:
    try:
        if isinstance(properties, bytes):
            soup = BeautifulSoup(properties, features="html.parser")
            properties = properties.decode(
                encoding=soup.original_encoding, errors="ignore"
            )
        if isinstance(properties, dict):
            # handle case where nested childs are dicts or list but provided with "" but have to be expanded.
            for key, value in properties.items():
                if isinstance(value, str) and value.startswith(("[", "{")):
                    properties[key] = json.loads(value, strict=False)
            return properties
    except JSONDecodeError as e:
        print(e)
        print(f"Couldn't decode dictionary. type={type(properties).__name__}, value={str(properties)[:300]}")
        return {}

    try:
        return json.loads(properties, strict=False)
    except JSONDecodeError as e:
        print(e)
        print(f"Couldn't decode dictionary (json.loads). type={type(properties).__name__}, value={str(properties)[:300]}")
        return {}


def decode_timestamp(content_utf8_encoded: str) -> datetime:
    if content_utf8_encoded is None:
        return None
    content_str = str(content_utf8_encoded).strip()
    if not content_str:
        return None
    try:
        # Try Unix epoch milliseconds as int (e.g., "1721365995912")
        return datetime.utcfromtimestamp(int(content_str) / 1000)
    except (ValueError, OSError, OverflowError):
        pass
    try:
        # Try ISO 8601 format (e.g., "2024-07-19T04:53:15.912Z")
        return datetime.fromisoformat(content_str.replace("Z", "+00:00"))
    except (ValueError, OSError):
        pass
    try:
        # Try as float - could be seconds or milliseconds
        float_val = float(content_str)
        # If value > year 2100 in seconds (~4102444800), it's likely milliseconds
        if float_val > 4102444800:
            return datetime.utcfromtimestamp(float_val / 1000)
        return datetime.utcfromtimestamp(float_val)
    except (ValueError, OSError, OverflowError) as e:
        pass
    print(f"Warning: Could not parse timestamp: {content_str}")
    return None


def encode_timestamp(timestamp: Optional[datetime]) -> Optional[str]:
    if timestamp is not None:
        return timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")
    return None


@dataclass_json(letter_case=LetterCase.CAMEL, undefined=Undefined.EXCLUDE)
@dataclass()
class Meeting(DataClassJsonMixin):
    client_update_time: Optional[str] = None
    cached_deduplication_key: Optional[str] = None
    id: Optional[str] = None
    members: Optional[list[dict]] = None
    thread_properties: dict[str, Any] = field(
        default_factory=dict, metadata=config(decoder=decode_dict)
    )
    type: Optional[str] = None
    version: Optional[float] = None

    record_type: Optional[str] = field(
        default="meeting", metadata=config(field_name="record_type")
    )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Meeting):
            return NotImplemented
        return self.cached_deduplication_key == other.cached_deduplication_key

    def __hash__(self) -> int:
        return hash(self.cached_deduplication_key)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Meeting):
            return NotImplemented
        return self.cached_deduplication_key < other.cached_deduplication_key


@dataclass_json(letter_case=LetterCase.CAMEL, undefined=Undefined.EXCLUDE)
@dataclass()
class Message(DataClassJsonMixin):
    attachments: list[Any] = field(default_factory=list)
    cached_deduplication_key: Optional[str] = None
    client_arrival_time: Optional[str] = None
    clientmessageid: Optional[str] = None
    composetime: Optional[str] = None
    conversation_id: Optional[str] = None
    content: Optional[str] = field(
        default=None, metadata=config(decoder=strip_html_tags)
    )
    contenttype: Optional[str] = None
    created_time: Optional[datetime] = field(
        default=None,
        metadata=config(decoder=decode_timestamp, encoder=encode_timestamp),
    )
    creator: Optional[str] = None
    is_from_me: Optional[bool] = None
    message_kind: Optional[str] = None
    messagetype: Optional[str] = None
    original_arrival_time: Optional[str] = None
    properties: dict[str, Any] = field(
        default_factory=dict, metadata=config(decoder=decode_dict)
    )
    version: Optional[datetime] = field(
        default=None,
        metadata=config(decoder=decode_timestamp, encoder=encode_timestamp),
    )

    origin_file: Optional[str] = field(
        default=None, metadata=config(field_name="origin_file")
    )
    record_type: str = field(
        default="message", metadata=config(field_name="record_type")
    )

    def __post_init__(self) -> None:
        if self.cached_deduplication_key is None:
            self.cached_deduplication_key = str(self.creator) + str(
                self.clientmessageid
            )
        # change record type depending on properties
        if "call-log" in self.properties:
            self.record_type = "call"
        if "activity" in self.properties:
            self.record_type = "reaction"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Message):
            return NotImplemented
        return self.cached_deduplication_key == other.cached_deduplication_key

    def __hash__(self) -> int:
        return hash(self.cached_deduplication_key)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Message):
            return NotImplemented
        return self.cached_deduplication_key < other.cached_deduplication_key

@dataclass_json(letter_case=LetterCase.CAMEL, undefined=Undefined.EXCLUDE)
@dataclass()
class EventCall(DataClassJsonMixin):
    # Message とほぼ同じ構造だが、content は strip_html_tags を適用せず生の XML をそのまま保持する。
    # messagetype "Event/Call" 用のクラスで、会議セッションの開始/終了情報が
    # XML 形式で content に格納されている (例: <callEventType>callStarted</callEventType>、<ended/>)。
    # アプリ側で content の XML を解析してセッション時刻を取り出す前提。
    attachments: list[Any] = field(default_factory=list)
    cached_deduplication_key: Optional[str] = None
    client_arrival_time: Optional[str] = None
    clientmessageid: Optional[str] = None
    composetime: Optional[str] = None
    conversation_id: Optional[str] = None
    content: Optional[str] = None  # 生の XML を保持 (strip_html_tags は適用しない)
    contenttype: Optional[str] = None
    created_time: Optional[datetime] = field(
        default=None,
        metadata=config(decoder=decode_timestamp, encoder=encode_timestamp),
    )
    creator: Optional[str] = None
    is_from_me: Optional[bool] = None
    message_kind: Optional[str] = None
    messagetype: Optional[str] = None
    original_arrival_time: Optional[str] = None
    properties: dict[str, Any] = field(
        default_factory=dict, metadata=config(decoder=decode_dict)
    )
    version: Optional[datetime] = field(
        default=None,
        metadata=config(decoder=decode_timestamp, encoder=encode_timestamp),
    )

    origin_file: Optional[str] = field(
        default=None, metadata=config(field_name="origin_file")
    )
    record_type: str = field(
        default="event_call", metadata=config(field_name="record_type")
    )

    def __post_init__(self) -> None:
        if self.cached_deduplication_key is None:
            self.cached_deduplication_key = str(self.creator) + str(
                self.clientmessageid
            )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EventCall):
            return NotImplemented
        return self.cached_deduplication_key == other.cached_deduplication_key

    def __hash__(self) -> int:
        return hash(self.cached_deduplication_key)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, EventCall):
            return NotImplemented
        return self.cached_deduplication_key < other.cached_deduplication_key


@dataclass_json(letter_case=LetterCase.CAMEL, undefined=Undefined.EXCLUDE)
@dataclass()
class TopicUpdate(DataClassJsonMixin):
    # messagetype "ThreadActivity/TopicUpdate" 用のクラス。会議名変更を記録する。
    # content の XML (例: <topicupdate><value>新トピック名</value></topicupdate>) から
    # 新トピック名を parser 側で抽出し `topic` フィールドに格納する。
    # アプリ側はセッション開始時刻と originalArrivalTime を比較して「当時の会議名」を復元する前提。
    cached_deduplication_key: Optional[str] = None
    clientmessageid: Optional[str] = None
    composetime: Optional[str] = None
    conversation_id: Optional[str] = None
    content: Optional[str] = None  # 生の XML を保持 (デバッグ用)
    contenttype: Optional[str] = None
    creator: Optional[str] = None
    is_from_me: Optional[bool] = None
    messagetype: Optional[str] = None
    original_arrival_time: Optional[str] = None
    topic: Optional[str] = None  # content から抽出した新トピック名

    origin_file: Optional[str] = field(
        default=None, metadata=config(field_name="origin_file")
    )
    record_type: str = field(
        default="topic_update", metadata=config(field_name="record_type")
    )

    def __post_init__(self) -> None:
        if self.cached_deduplication_key is None:
            self.cached_deduplication_key = str(self.creator) + str(
                self.clientmessageid
            )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TopicUpdate):
            return NotImplemented
        return self.cached_deduplication_key == other.cached_deduplication_key

    def __hash__(self) -> int:
        return hash(self.cached_deduplication_key)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, TopicUpdate):
            return NotImplemented
        return self.cached_deduplication_key < other.cached_deduplication_key


@dataclass_json(letter_case=LetterCase.CAMEL, undefined=Undefined.EXCLUDE)
@dataclass()
class Contact(DataClassJsonMixin):
    display_name: Optional[str] = None
    email: Optional[str] = None
    mri: Optional[str] = field(default=None, compare=True)
    user_principal_name: Optional[str] = None

    origin_file: Optional[str] = field(
        default=None, metadata=config(field_name="origin_file")
    )
    record_type: Optional[str] = field(
        default="contact", metadata=config(field_name="record_type")
    )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Contact):
            return NotImplemented
        return self.mri == other.mri

    def __hash__(self) -> int:
        return hash(self.mri)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Contact):
            return NotImplemented
        return self.mri < other.mri


def _parse_people(people: list[dict], version: str) -> set[Contact]:
    parsed_people = set()

    for p in people:
        p_value = p.get("value")

        # v2 では "value" キーがない場合、レコード自体にデータが格納されている
        if p_value is None and version in ("v1", "v2"):
            p_value = p

        if p_value is not None and isinstance(p_value, dict) and version in ("v1", "v2"):
            # v1: mri キーが直接存在する
            # v2: mri がなく、id や EmailAddresses を使用する
            email = (
                p_value.get("email")
                or p_value.get("emailAddress")
                or p_value.get("userPrincipalName")
                or p_value.get("UserPrincipalName")
                or p_value.get("sipAddress")
                or p_value.get("SipAddress")
            )
            if not email:
                email_addresses = (
                    p_value.get("EmailAddresses")
                    or p_value.get("emailAddresses")
                    or []
                )
                if isinstance(email_addresses, list) and email_addresses:
                    email = email_addresses[0]

            mri = (
                p_value.get("mri")
                or p_value.get("MRI")
                or p_value.get("objectId")
                or p_value.get("ObjectId")
                or p_value.get("ExternalDirectoryObjectId")
                or p_value.get("id")
                or p_value.get("Id")
                or p_value.get("userId")
                or p_value.get("UserId")
                or email
            )

            display_name = (
                p_value.get("displayName")
                or p_value.get("DisplayName")
                or p_value.get("display_name")
            )
            if not display_name:
                given = p_value.get("givenName") or p_value.get("GivenName") or ""
                surname = p_value.get("surname") or p_value.get("Surname") or ""
                display_name = f"{given} {surname}".strip() or None

            if mri is not None:
                contact_dict = {
                    "mri": mri,
                    "email": email,
                    "displayName": display_name,
                    "userPrincipalName": p_value.get("userPrincipalName"),
                    "origin_file": p.get("origin_file"),
                }
                try:
                    parsed_people.add(Contact.from_dict(contact_dict))
                except Exception as e:
                    print(f"Warning: Skipping people record: {type(e).__name__}: {e}")
        else:
            logging.warning(
                "Teams Version is unknown or record incomplete. Can not extract records of type people."
            )

    return parsed_people


def _parse_buddies(buddies: list[dict], version: str) -> set[Contact]:
    parsed_buddies = set()

    for b in buddies:
        b_value = b.get("value", {})
        if b_value and version in ("v1", "v2"):
            buddies_of_b = b_value.get("buddies", [])
            for b_of_b in buddies_of_b:
                parsed_buddies.add(Contact.from_dict(b_of_b))
        else:
            logging.warning(
                "Teams Version is unknown. Can not extract records of type buddies."
            )
    return parsed_buddies


def _parse_conversations(conversations: list[dict], version: str) -> set[Meeting]:
    cleaned_conversations: set[Meeting] = set()

    # version が unknown の場合は meeting レコードを抽出できない。
    # 各レコードごとに warning を出すと大量のノイズになるため、件数情報付きで 1 回だけ警告する。
    # (本当に unknown なケースは identify_teams_version 側でも詳細な warning が出ている)
    if version not in ("v1", "v2"):
        if conversations:
            logging.warning(
                f"_parse_conversations: skipped {len(conversations)} conversation record(s) "
                f"because Teams version is unknown."
            )
        return cleaned_conversations

    for c in conversations:
        value = c.get("value", {})
        thread_properties = value.get("threadProperties", {})
        # Conversations ストアには meeting 以外 (通常のチャットスレッド等) も含まれる。
        # meeting キーを持たないレコードは警告を出さず silent skip する (取りこぼしではなく仕様)。
        if "meeting" not in thread_properties:
            continue

        c |= value
        c |= {"cached_deduplication_key": c.get("id")}
        try:
            cleaned_conversations.add(Meeting.from_dict(c))
        except (ValueError, TypeError, KeyError, OSError, OverflowError) as e:
            print(f"Warning: Skipping meeting due to parsing error: {e}")
    return cleaned_conversations


def _parse_reply_chains(reply_chains: list[dict], version: str) -> set[Message]:
    cleaned_reply_chains = set()

    for rc in reply_chains:
        rc_value = rc.get("value", {})

        # Skip empty records
        if not rc_value:
            continue

        # Fetch relevant data
        rc |= rc_value
        message_dict = {}
        if version == "v1":
            message_dict = rc_value.get("messages", {})
        elif version == "v2":
            message_dict = rc_value.get("messageMap", {})
        else:
            logging.warning(
                "Teams Version is unknown. Can not extract records of type reply_chains."
            )
            continue

        for k in message_dict:
            md = message_dict[k]
            if md.get("messagetype", "") in ("RichText/Html", "Text") or md.get(
                "messageType"
            ) in ("RichText/Html", "Text"):
                rc |= md
                if version == "v1":
                    rc |= {"original_arrival_time": md.get("originalarrivaltime")}
                # map to teams 1.x keys
                if version == "v2":
                    rc |= {"cached_deduplication_key": md.get("dedupeKey")}
                    rc |= {"clientmessageid": md.get("clientMessageId")}
                    # set to clientArrivalTime as compose time is no longer present
                    rc |= {"composetime": md.get("clientArrivalTime")}
                    rc |= {"contenttype": md.get("contentType")}
                    # set to clientArrivalTime as created time is no longer present
                    rc |= {"created_time": md.get("clientArrivalTime")}
                    rc |= {"is_from_me": md.get("isSentByCurrentUser")}
                    rc |= {"messagetype": md.get("messageType")}

                try:
                    cleaned_reply_chains.add(Message.from_dict(rc))
                except (ValueError, TypeError, KeyError, OSError, OverflowError) as e:
                    print(f"Warning: Skipping message due to parsing error: {e}")
                    continue

    return cleaned_reply_chains


def _parse_event_calls(reply_chains: list[dict], version: str) -> set[EventCall]:
    # reply_chains から messagetype "Event/Call" のレコードを抽出する。
    # 会議の各セッションは callStarted と ended のペアで記録される。
    # content の XML はそのまま保持し、セッション時刻はアプリ側で解析する。
    cleaned_event_calls: set[EventCall] = set()

    if version not in ("v1", "v2"):
        # version が unknown の場合は _parse_reply_chains 側ですでに警告が出ているのでここでは黙る
        return cleaned_event_calls

    for rc in reply_chains:
        rc_value = rc.get("value", {})
        if not rc_value:
            continue

        message_dict: dict = {}
        if version == "v1":
            message_dict = rc_value.get("messages", {}) or {}
        else:  # v2
            message_dict = rc_value.get("messageMap", {}) or {}

        if not message_dict:
            continue

        for k, md in message_dict.items():
            if not isinstance(md, dict):
                continue

            # 防御的: messagetype は v1/v2 でキー名が違うので両方を取得して片方が取れた値を採用
            mtype = md.get("messagetype") or md.get("messageType") or ""
            if mtype != "Event/Call":
                continue

            # 必須: content (XML 本体) が無いレコードはスキップ
            if not md.get("content"):
                logging.warning(
                    f"event_call has empty content: id={md.get('id')}"
                )
                continue

            # _parse_reply_chains と同じパターンで rc / rc_value / md をマージ
            merged = dict(rc)
            merged.update(rc_value)
            merged.update(md)

            if version == "v1":
                merged["original_arrival_time"] = md.get("originalarrivaltime")
            else:  # v2
                merged["cached_deduplication_key"] = md.get("dedupeKey")
                merged["clientmessageid"] = md.get("clientMessageId")
                merged["composetime"] = md.get("clientArrivalTime")
                merged["contenttype"] = md.get("contentType")
                merged["created_time"] = md.get("clientArrivalTime")
                merged["is_from_me"] = md.get("isSentByCurrentUser")
                merged["messagetype"] = md.get("messageType")

            try:
                cleaned_event_calls.add(EventCall.from_dict(merged))
            except (ValueError, TypeError, KeyError, OSError, OverflowError) as e:
                logging.warning(
                    f"Skipping event_call due to parsing error: id={md.get('id')}, err={e}"
                )
                continue

    return cleaned_event_calls


def _extract_topic_from_content(content: str) -> Optional[str]:
    # ThreadActivity/TopicUpdate の content XML から <value>...</value> の中身を抽出する。
    # 期待形式: <topicupdate><eventtime>...</eventtime><initiator>...</initiator><value>新トピック名</value></topicupdate>
    # 形式が崩れている / <value> が存在しない場合は None を返す (呼び出し側で warning + スキップ)。
    if not content:
        return None
    try:
        soup = BeautifulSoup(content, features="html.parser")
        value_tag = soup.find("value")
        if value_tag is None:
            return None
        text = value_tag.get_text()
        return text if text else None
    except Exception as e:
        logging.warning(f"_extract_topic_from_content: parse error: {e}")
        return None


def _parse_topic_updates(reply_chains: list[dict], version: str) -> set[TopicUpdate]:
    # reply_chains から messagetype "ThreadActivity/TopicUpdate" のレコードを抽出する。
    # 会議名変更を時系列で追跡するためのレコードで、各セッションを「そのセッション開始時点で
    # 有効だった会議名」で表示するために使う。
    cleaned_topic_updates: set[TopicUpdate] = set()

    if version not in ("v1", "v2"):
        # version が unknown の場合は _parse_reply_chains 側ですでに警告が出ているのでここでは黙る
        return cleaned_topic_updates

    for rc in reply_chains:
        rc_value = rc.get("value", {})
        if not rc_value:
            continue

        message_dict: dict = {}
        if version == "v1":
            message_dict = rc_value.get("messages", {}) or {}
        else:  # v2
            message_dict = rc_value.get("messageMap", {}) or {}

        if not message_dict:
            continue

        for k, md in message_dict.items():
            if not isinstance(md, dict):
                continue

            # 防御的: messagetype は v1/v2 でキー名が違うので両方を取得して片方が取れた値を採用
            mtype = md.get("messagetype") or md.get("messageType") or ""
            if mtype != "ThreadActivity/TopicUpdate":
                continue

            # 必須: content (XML 本体) が無いレコードはスキップ
            content = md.get("content")
            if not content:
                logging.warning(
                    f"topic_update has empty content: id={md.get('id')}"
                )
                continue

            # XML から新トピック名を抽出 (失敗時は warning + 該当レコードのみスキップ)
            topic = _extract_topic_from_content(content)
            if not topic:
                logging.warning(
                    f"topic_update could not extract topic from content: "
                    f"id={md.get('id')}, content_head={content[:120]!r}"
                )
                continue

            # _parse_event_calls と同じパターンで rc / rc_value / md をマージ
            merged = dict(rc)
            merged.update(rc_value)
            merged.update(md)
            merged["topic"] = topic  # 抽出した新トピック名を格納

            if version == "v1":
                merged["original_arrival_time"] = md.get("originalarrivaltime")
            else:  # v2
                merged["cached_deduplication_key"] = md.get("dedupeKey")
                merged["clientmessageid"] = md.get("clientMessageId")
                merged["composetime"] = md.get("clientArrivalTime")
                merged["contenttype"] = md.get("contentType")
                merged["created_time"] = md.get("clientArrivalTime")
                merged["is_from_me"] = md.get("isSentByCurrentUser")
                merged["messagetype"] = md.get("messageType")

            try:
                cleaned_topic_updates.add(TopicUpdate.from_dict(merged))
            except (ValueError, TypeError, KeyError, OSError, OverflowError) as e:
                logging.warning(
                    f"Skipping topic_update due to parsing error: id={md.get('id')}, err={e}"
                )
                continue

    return cleaned_topic_updates


def identify_teams_version(reply_chains: list[dict]) -> str:
    # reply_chain の構造からバージョン (v1 / v2) を判定する。
    # 空レコードが混じるので先頭 50 件を順に調べる。
    # 既知のキー (messages / messageMap) がどれも見つからず、それでも非空の value 辞書が
    # 存在した場合は、そこにあるキー一覧を warning で記録する。
    # これにより将来 Teams が新フォーマット (例: 仮称 v3) を導入した際に、
    # 新しいキー名がログに残り、対応すべき内容をすぐに把握できるようにする。
    unknown_samples: list[list[str]] = []
    for i, rc in enumerate(reply_chains[:50]):
        rc_value = rc.get("value", {})
        if not rc_value or not isinstance(rc_value, dict):
            continue
        if rc_value.get("messages", {}):
            return "v1"
        if rc_value.get("messageMap", {}):
            return "v2"

        # value 辞書は非空だが、既知のどのキーも持たない。
        # 将来の新フォーマットの可能性があるので、診断用にサンプルとしてキー一覧を残す。
        if len(unknown_samples) < 3:
            unknown_samples.append(sorted(rc_value.keys()))

    # 先頭 50 件で既知の構造が見つからなかった。
    if unknown_samples:
        logging.warning(
            "identify_teams_version: unknown structure. "
            f"sample value keys (up to 3 records): {unknown_samples}"
        )
    return "unknown"


def parse_records(records: list[dict]) -> list[dict]:
    people, buddies, reply_chains, conversations = [], [], [], []

    for r in records:
        store = r.get("store", "other")
        if store == "people":
            people.append(r)
        elif store == "buddylist":
            buddies.append(r)
        elif store == "replychains":
            reply_chains.append(r)
        elif store == "conversations":
            conversations.append(r)

    # identify version
    version = identify_teams_version(reply_chains)

    # 種類ごとにソート (Contacts / Meetings / Conversations / Event/Call / TopicUpdate) してから連結
    parsed_records = (
        sorted(_parse_people(people, version))
        + sorted(_parse_buddies(buddies, version))
        + sorted(_parse_reply_chains(reply_chains, version))
        + sorted(_parse_conversations(conversations, version))
        + sorted(_parse_event_calls(reply_chains, version))
        + sorted(_parse_topic_updates(reply_chains, version))
    )
    return [r.to_dict() for r in parsed_records]


def process_db(
    input_path: Path,
    output_path: Path,
    blob_path: Optional[Path] = None,
    filter_db_results: Optional[bool] = True,
) -> None:
    if not input_path.parts[-1].endswith(".leveldb"):
        raise ValueError(f"Expected a leveldb folder. Path: {input_path}")

    if blob_path is not None and not blob_path.parts[-1].endswith(".blob"):
        raise ValueError(f"Expected a .blob folder. Path: {blob_path}")

    extracted_values = parse_db(input_path, blob_path, filter_db_results)
    parsed_records = parse_records(extracted_values)
    write_results_to_json(parsed_records, output_path)
