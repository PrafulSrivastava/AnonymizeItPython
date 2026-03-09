"""
DLT Log Parser.

Supports two input formats produced by the COVESA dlt-daemon toolchain:

1. Text export from DLT Viewer (.txt / .csv)
   The canonical column layout exported by DLT Viewer 2.x is:

     <index>  <abs_timestamp>  <rel_timestamp>  <ecu>  <app>  <ctx>
              <type>  <subtype>  <mode>  <#args>  <payload...>

   Example:
       1    0.000000    0.000000 ECU1 APP1 CTX1 log info verbose 1 Hello World

   DLT Viewer 1.x / some exporters prepend a wall-clock date:

       2023/01/01 12:34:56.789  42 001 ECU1 APP1 CTX1 log info verbose 1 Msg

2. Raw binary .dlt files are parsed via the optional `python-dlt` package.
   If that package is not installed the scanner falls back to text-only mode
   and prints a warning.
"""

from __future__ import annotations

import re
import struct
import datetime
from dataclasses import dataclass, field
from typing import Iterator, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DltEntry:
    """One parsed DLT log entry."""
    index: int                         # sequential row number (1-based)
    ecu_id: str = ""                   # ECU identifier, e.g. "ECU1"
    app_id: str = ""                   # Application ID, e.g. "APP1"
    ctx_id: str = ""                   # Context ID, e.g. "CTX1"
    log_level: str = ""                # e.g. "info", "warn", "error"
    message_type: str = ""             # "log", "control", "network", "app_trace"
    timestamp: Optional[float] = None  # absolute timestamp in seconds
    payload: str = ""                  # the actual log message text
    raw_line: str = ""                 # original line (for audit)
    source_file: str = ""              # path of the source file


# ---------------------------------------------------------------------------
# Text-format parser
# ---------------------------------------------------------------------------

# DLT Viewer text-export column separator is variable whitespace.
# The log-level sub-field can be: fatal/error/warn/info/debug/verbose/off
_LOG_LEVELS = r"(?:fatal|error|warn|info|debug|verbose|off)"
_MSG_TYPES  = r"(?:log|control|network_trace|app_trace|network)"

# Pattern A – pure numeric timestamp (DLT Viewer 2.x default export)
# Groups: (index, abs_ts, rel_ts, ecu, app, ctx, msg_type, log_level, mode, nargs, payload)
_PAT_A = re.compile(
    r"^\s*(\d+)\s+"                        # index
    r"([\d.]+)\s+"                         # abs timestamp (s.ms)
    r"([\d.]+)\s+"                         # rel timestamp
    r"(\S{1,4})\s+"                        # ECU ID
    r"(\S{1,4})\s+"                        # App ID
    r"(\S{1,4})\s+"                        # Context ID
    r"("  + _MSG_TYPES  + r")\s+"          # message type
    + r"(" + _LOG_LEVELS + r")\s+"         # log level/subtype
    r"\S+\s+"                              # mode (verbose/non-verbose, discard)
    r"\d+\s+"                              # number of arguments (discard)
    r"(.*)",                               # payload (rest of line)
    re.IGNORECASE,
)

# Pattern B – wall-clock prefix (some DLT Viewer exporters and dlt-convert -a)
# E.g.: "2023/01/01 12:34:56.789012   42 001 ECU1 APP1 CTX1 log info verbose 1 msg"
_PAT_B = re.compile(
    r"^\s*(\d{4}[/\-]\d{2}[/\-]\d{2})\s+"  # date (discard)
    r"([\d:.]+)\s+"                          # time (discard)
    r"(\d+)\s+"                              # index
    r"\d+\s+"                                # session id / counter (discard)
    r"(\S{1,4})\s+"                          # ECU ID
    r"(\S{1,4})\s+"                          # App ID
    r"(\S{1,4})\s+"                          # Context ID
    r"("  + _MSG_TYPES  + r")\s+"           # message type
    r"(" + _LOG_LEVELS  + r")\s+"           # log level
    r"\S+\s+"                               # mode
    r"\d+\s+"                               # nargs
    r"(.*)",                                # payload
    re.IGNORECASE,
)

# Pattern C – minimal / legacy format (index  timestamp  ecu  app  ctx  payload)
_PAT_C = re.compile(
    r"^\s*(\d+)\s+"                         # index
    r"([\d.]+)\s+"                          # timestamp
    r"(\S{1,4})\s+"                         # ECU
    r"(\S{1,4})\s+"                         # App
    r"(\S{1,4})\s+"                         # Ctx
    r"(.*)",                                # payload
    re.IGNORECASE,
)

# Skip header / separator lines
_SKIP_PATTERN = re.compile(
    r"^\s*(?:Index|#|---|\s*$|={3,}|Timestamp|Date)", re.IGNORECASE
)


def _try_parse_text_line(line: str, fallback_index: int) -> Optional[DltEntry]:
    """Try every known text-format pattern; return DltEntry or None."""
    # Skip blank lines and header rows
    if _SKIP_PATTERN.match(line):
        return None

    m = _PAT_A.match(line)
    if m:
        return DltEntry(
            index=int(m.group(1)),
            timestamp=float(m.group(2)),
            ecu_id=m.group(4).strip(),
            app_id=m.group(5).strip(),
            ctx_id=m.group(6).strip(),
            message_type=m.group(7).lower(),
            log_level=m.group(8).lower(),
            payload=m.group(9).strip(),
            raw_line=line.rstrip(),
        )

    m = _PAT_B.match(line)
    if m:
        return DltEntry(
            index=int(m.group(3)),
            ecu_id=m.group(4).strip(),
            app_id=m.group(5).strip(),
            ctx_id=m.group(6).strip(),
            message_type=m.group(7).lower(),
            log_level=m.group(8).lower(),
            payload=m.group(9).strip(),
            raw_line=line.rstrip(),
        )

    m = _PAT_C.match(line)
    if m:
        return DltEntry(
            index=int(m.group(1)),
            timestamp=float(m.group(2)),
            ecu_id=m.group(3).strip(),
            app_id=m.group(4).strip(),
            ctx_id=m.group(5).strip(),
            payload=m.group(6).strip(),
            raw_line=line.rstrip(),
        )

    return None


def parse_text_file(path: str, encoding: str = "utf-8") -> Iterator[DltEntry]:
    """
    Yield DltEntry objects from a DLT Viewer text export.

    Lines that cannot be parsed (continuation lines, binary blobs printed as
    hex, etc.) are silently skipped – this keeps the scanner robust against
    imperfect exports.
    """
    fallback_index = 0
    try:
        fh = open(path, "r", encoding=encoding, errors="replace")
    except OSError as exc:
        raise ValueError(f"Cannot open '{path}': {exc}") from exc

    with fh:
        for line in fh:
            fallback_index += 1
            entry = _try_parse_text_line(line, fallback_index)
            if entry is not None:
                entry.source_file = path
                yield entry


# ---------------------------------------------------------------------------
# Binary .dlt parser  (AUTOSAR DLT spec, storage-header format)
# ---------------------------------------------------------------------------
#
# Binary DLT file structure (each message):
#   Storage Header (16 bytes):
#     4 bytes  – pattern "DLT\x01"
#     4 bytes  – seconds (big-endian uint32)
#     4 bytes  – microseconds (big-endian int32)
#     4 bytes  – ECU ID (ASCII, zero-padded)
#
#   Standard Header (4+ bytes):
#     1 byte   – header type bitmask
#     1 byte   – message counter
#     2 bytes  – length (big-endian uint16, includes ext+payload)
#     [4 bytes – ECU ID if HTYP bit 0 set]
#     [4 bytes – session ID if HTYP bit 1 set]
#     [4 bytes – timestamp (0.1 ms units) if HTYP bit 2 set]
#
#   Extended Header (10 bytes, if HTYP bit 5 set):
#     1 byte   – message info (message type in bits 1-3, verbose in bit 0)
#     1 byte   – number of arguments
#     4 bytes  – App ID
#     4 bytes  – Context ID
#
#   Payload: variable length (series of typed DLT arguments)
#

_DLT_STORAGE_MAGIC = b"DLT\x01"
_STORAGE_HDR_SIZE  = 16

# Standard header bit flags
_HTYP_ECU_ID    = 0x04
_HTYP_SESSION   = 0x08
_HTYP_TIMESTAMP = 0x10
_HTYP_EXT_HDR   = 0x01

# Extended header message type mask (bits 1-3)
_MTIN_LOG       = 0x00  # log message
_MSTP_MASK      = 0x0E  # bits 1-3
_VERBOSE_BIT    = 0x01

_LOG_LEVEL_NAMES = {1: "fatal", 2: "error", 3: "warn",
                    4: "info",  5: "debug", 6: "verbose"}
_MSG_TYPE_NAMES  = {0: "log", 1: "app_trace", 2: "network_trace",
                    3: "control"}

# DLT argument type identifiers (4-byte type info field, bit layout)
_TYPE_BOOL  = 0x00000010
_TYPE_SINT  = 0x00000020
_TYPE_UINT  = 0x00000040
_TYPE_FLOA  = 0x00000080
_TYPE_ARAY  = 0x00000100
_TYPE_STRG  = 0x00000200
_TYPE_RAWD  = 0x00000400
_TYPE_TRAI  = 0x00000800
_TYPE_FIXP  = 0x00001000
_TYPE_VARI  = 0x00020000  # variable info (name + unit included)
_TYPE_FIXP  = 0x00001000
_STRG_UTF8  = 0x00008000  # string encoding bit


def _read_exact(fh, n: int) -> bytes:
    data = fh.read(n)
    if len(data) < n:
        raise EOFError
    return data


def _decode_payload_verbose(data: bytes) -> str:
    """
    Decode verbose DLT payload into a human-readable string.
    Each argument is prefixed by a 4-byte type-info word.
    Unknown types are rendered as hex.
    """
    parts: list[str] = []
    pos = 0
    while pos + 4 <= len(data):
        type_info = struct.unpack_from("<I", data, pos)[0]
        pos += 4

        if type_info & _TYPE_VARI:
            # Skip variable name: 2-byte length + string + 2-byte unit length + string
            if pos + 2 > len(data):
                break
            name_len = struct.unpack_from("<H", data, pos)[0]; pos += 2
            pos += name_len  # skip name bytes
            if pos + 2 > len(data):
                break
            unit_len = struct.unpack_from("<H", data, pos)[0]; pos += 2
            pos += unit_len

        if type_info & _TYPE_BOOL:
            if pos + 1 > len(data):
                break
            parts.append("true" if data[pos] else "false")
            pos += 1

        elif type_info & _TYPE_STRG:
            if pos + 2 > len(data):
                break
            slen = struct.unpack_from("<H", data, pos)[0]; pos += 2
            if pos + slen > len(data):
                break
            raw = data[pos:pos + slen]
            pos += slen
            enc = "utf-8" if (type_info & _STRG_UTF8) else "latin-1"
            parts.append(raw.rstrip(b"\x00").decode(enc, errors="replace"))

        elif type_info & _TYPE_SINT:
            # Determine size from bits 4-7 (length code)
            sz = 1 << ((type_info >> 4) & 0x0F)  # 1/2/4/8 bytes
            if pos + sz > len(data):
                break
            fmt = {1: "<b", 2: "<h", 4: "<i", 8: "<q"}.get(sz, "<i")
            parts.append(str(struct.unpack_from(fmt, data, pos)[0]))
            pos += sz

        elif type_info & _TYPE_UINT:
            sz = 1 << ((type_info >> 4) & 0x0F)
            if pos + sz > len(data):
                break
            fmt = {1: "<B", 2: "<H", 4: "<I", 8: "<Q"}.get(sz, "<I")
            parts.append(str(struct.unpack_from(fmt, data, pos)[0]))
            pos += sz

        elif type_info & _TYPE_FLOA:
            sz = 1 << ((type_info >> 4) & 0x0F)
            if pos + sz > len(data):
                break
            fmt = {4: "<f", 8: "<d"}.get(sz, "<f")
            parts.append(str(struct.unpack_from(fmt, data, pos)[0]))
            pos += sz

        elif type_info & _TYPE_RAWD:
            if pos + 2 > len(data):
                break
            rlen = struct.unpack_from("<H", data, pos)[0]; pos += 2
            if pos + rlen > len(data):
                break
            parts.append(data[pos:pos + rlen].hex())
            pos += rlen

        else:
            # Unknown type: skip remainder to avoid infinite loop
            break

    return " ".join(parts)


def _decode_payload_non_verbose(data: bytes) -> str:
    """Non-verbose payloads start with a 4-byte message ID; rest is opaque."""
    if len(data) < 4:
        return data.hex()
    msg_id = struct.unpack_from(">I", data)[0]
    rest = data[4:]
    text = rest.decode("utf-8", errors="replace").rstrip("\x00")
    return f"[msgid={msg_id:#010x}] {text}" if text else f"[msgid={msg_id:#010x}]"


def parse_binary_file(path: str) -> Iterator[DltEntry]:
    """
    Yield DltEntry objects from a binary .dlt file (storage-header format).

    This is a best-effort parser: malformed or partial messages are skipped
    so that a single corrupt entry does not abort the whole file scan.
    """
    index = 0
    try:
        fh = open(path, "rb")
    except OSError as exc:
        raise ValueError(f"Cannot open '{path}': {exc}") from exc

    with fh:
        while True:
            try:
                # Seek to next storage header magic
                magic = fh.read(4)
                if not magic:
                    break  # EOF

                if magic != _DLT_STORAGE_MAGIC:
                    # Resync: read byte-by-byte until we find the magic
                    buf = magic
                    while len(buf) >= 4:
                        if buf[-4:] == _DLT_STORAGE_MAGIC:
                            break
                        next_byte = fh.read(1)
                        if not next_byte:
                            return
                        buf += next_byte
                    else:
                        continue

                # Storage header: seconds (4), microseconds (4), ECU (4)
                storage_rest = _read_exact(fh, 12)
                seconds      = struct.unpack_from(">I", storage_rest, 0)[0]
                microseconds = struct.unpack_from(">i", storage_rest, 4)[0]
                ecu_id_bytes = storage_rest[8:12].rstrip(b"\x00")
                ecu_id       = ecu_id_bytes.decode("ascii", errors="replace")
                timestamp    = seconds + microseconds / 1_000_000

                # Standard header
                std_hdr_byte0 = _read_exact(fh, 4)
                htyp     = std_hdr_byte0[0]
                msg_cnt  = std_hdr_byte0[1]
                msg_len  = struct.unpack_from(">H", std_hdr_byte0, 2)[0]

                # Remaining bytes expected after the first 4 standard header bytes
                remaining_len = msg_len - 4
                if remaining_len < 0:
                    continue  # malformed

                remaining = _read_exact(fh, remaining_len)
                pos = 0

                # Optional ECU ID in standard header
                if htyp & _HTYP_ECU_ID:
                    ecu_id = remaining[pos:pos+4].rstrip(b"\x00").decode("ascii", errors="replace")
                    pos += 4

                # Optional session ID
                if htyp & _HTYP_SESSION:
                    pos += 4

                # Optional timestamp (0.1 ms units)
                if htyp & _HTYP_TIMESTAMP:
                    ts_raw = struct.unpack_from(">I", remaining, pos)[0]
                    timestamp = ts_raw / 10_000.0  # convert to seconds
                    pos += 4

                # Extended header
                app_id = ""
                ctx_id = ""
                log_level = ""
                message_type = ""
                num_args = 0
                verbose = False

                if htyp & _HTYP_EXT_HDR:
                    if pos + 10 > len(remaining):
                        continue  # truncated
                    msin     = remaining[pos];     pos += 1
                    num_args = remaining[pos];     pos += 1
                    app_id   = remaining[pos:pos+4].rstrip(b"\x00").decode("ascii", errors="replace"); pos += 4
                    ctx_id   = remaining[pos:pos+4].rstrip(b"\x00").decode("ascii", errors="replace"); pos += 4

                    verbose      = bool(msin & _VERBOSE_BIT)
                    mstp         = (msin & _MSTP_MASK) >> 1
                    message_type = _MSG_TYPE_NAMES.get(mstp, "log")

                    if mstp == 0:  # log message
                        mtin      = (msin >> 4) & 0x0F
                        log_level = _LOG_LEVEL_NAMES.get(mtin, "")

                # Payload
                payload_data = remaining[pos:]
                if verbose:
                    payload = _decode_payload_verbose(payload_data)
                else:
                    payload = _decode_payload_non_verbose(payload_data)

                index += 1
                entry = DltEntry(
                    index=index,
                    ecu_id=ecu_id,
                    app_id=app_id,
                    ctx_id=ctx_id,
                    log_level=log_level,
                    message_type=message_type,
                    timestamp=timestamp,
                    payload=payload,
                    source_file=path,
                )
                yield entry

            except (EOFError, struct.error):
                break  # truncated file – stop gracefully


# ---------------------------------------------------------------------------
# Auto-detect and dispatch
# ---------------------------------------------------------------------------

def parse_file(path: str) -> Iterator[DltEntry]:
    """
    Auto-detect file format (.dlt binary vs text export) and yield DltEntry objects.
    Falls back to text parsing if the binary magic is absent.
    """
    try:
        with open(path, "rb") as fh:
            header = fh.read(4)
        is_binary = header == _DLT_STORAGE_MAGIC
    except OSError:
        is_binary = False

    if is_binary:
        yield from parse_binary_file(path)
    else:
        yield from parse_text_file(path)
