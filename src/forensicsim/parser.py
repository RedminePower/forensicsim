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
        print(f"[DIAG] Float timestamp failed: input_type={type(content_utf8_encoded).__name__}, content_str='{content_str}', error={e}")
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
    diag_printed = 0

    for p in people:
        # 診断: レコードのトップレベル構造を確認（最初の3件）
        if diag_printed < 3:
            diag_printed += 1
            print(f"[DIAG] people record top-level keys: {list(p.keys())[:20]}")
            for k in list(p.keys())[:15]:
                v = p[k]
                v_str = str(v)[:300] if v is not None else "None"
                print(f"[DIAG]   {k} = {v_str}")

        p_value = p.get("value")

        # v2 では "value" キーがない場合、レコード自体にデータが格納されている
        if p_value is None and version in ("v1", "v2"):
            # "value" がない場合、p 自体を p_value として扱う
            p_value = p

        if p_value is not None and version in ("v1", "v2"):
            # email の取得: v2 では emailAddresses (リスト) に格納されている
            email = (
                p_value.get("email")
                or p_value.get("emailAddress")
                or p_value.get("userPrincipalName")
                or p_value.get("sipAddress")
            )
            # emailAddresses はリスト形式
            if not email:
                email_addresses = p_value.get("emailAddresses", [])
                if isinstance(email_addresses, list) and email_addresses:
                    email = email_addresses[0]

            # mri の取得: v2 では mri がない場合、emailAddresses[0] を代用
            mri = (
                p_value.get("mri")
                or p_value.get("objectId")
                or p_value.get("id")
                or p_value.get("userId")
                or email  # email を mri の代わりに使用
            )
            if mri is not None:
                merged = p | p_value if p_value is not p else dict(p)
                merged["mri"] = mri
                if not merged.get("email"):
                    merged["email"] = email
                if not merged.get("displayName") and not merged.get("display_name"):
                    merged["displayName"] = (
                        p_value.get("displayName")
                        or p_value.get("display_name")
                        or (p_value.get("givenName", p_value.get("GivenName", "")) + " " + p_value.get("surname", p_value.get("Surname", ""))).strip()
                        or None
                    )
                try:
                    parsed_people.add(Contact.from_dict(merged))
                except (ValueError, TypeError, KeyError) as e:
                    print(f"Warning: Skipping people record: {e}")
        else:
            logging.warning(
                "Teams Version is unknown or record incomplete. Can not extract records of type people."
            )

    print(f"[DIAG] people: {len(people)} raw records -> {len(parsed_people)} contacts parsed")
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
    cleaned_conversations = set()

    for c in conversations:
        value = c.get("value", {})
        thread_properties = value.get("threadProperties", {})
        # Conversations can contain multiple artefacts. Filter only for meetings.
        if version in ("v1", "v2") and "meeting" in thread_properties:
            c |= value
            c |= {"cached_deduplication_key": c.get("id")}
            try:
                cleaned_conversations.add(Meeting.from_dict(c))
            except (ValueError, TypeError, KeyError, OSError, OverflowError) as e:
                print(f"Warning: Skipping meeting due to parsing error: {e}")
        else:
            logging.warning(
                "Teams Version is unknown. Can not extract records of type meeting."
            )
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


def identify_teams_version(reply_chains: list[dict]) -> str:
    # Identify version based on reply chain structure
    # Check multiple records since some may be empty
    for i, rc in enumerate(reply_chains[:50]):
        rc_value = rc.get("value", {})
        if not rc_value or not isinstance(rc_value, dict):
            continue
        if rc_value.get("messages", {}):
            print(f"[DIAG] Detected Teams version: v1 (from record {i})")
            return "v1"
        if rc_value.get("messageMap", {}):
            print(f"[DIAG] Detected Teams version: v2 (from record {i})")
            return "v2"

    # Log diagnostic info for the first non-empty record
    for i, rc in enumerate(reply_chains[:5]):
        rc_value = rc.get("value", {})
        if rc_value and isinstance(rc_value, dict):
            print(f"[DIAG] Version detection failed. Record {i} value keys: {list(rc_value.keys())[:30]}")
            for k in list(rc_value.keys())[:20]:
                v = rc_value[k]
                print(f"[DIAG]   key='{k}', type={type(v).__name__}, value={str(v)[:300]}")
            break

    print(f"[DIAG] Total reply_chains records: {len(reply_chains)}")
    print(f"[DIAG] Detected Teams version: unknown")
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

    # sort within groups i.e., Contacts, Meetings, Conversations
    parsed_records = (
        sorted(_parse_people(people, version))
        + sorted(_parse_buddies(buddies, version))
        + sorted(_parse_reply_chains(reply_chains, version))
        + sorted(_parse_conversations(conversations, version))
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
