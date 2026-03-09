"""
Generate a synthetic binary .dlt file (AUTOSAR DLT storage-header format)
that contains a realistic mix of log messages, including many with PII,
so the DLT scanner can be exercised thoroughly.

Run:
    python create_sample_dlt.py          # produces system.dlt
    python create_sample_dlt.py out.dlt  # custom output path
"""

from __future__ import annotations
import struct
import sys

# ────────────────────────────────────────────────────────────────────────────
# Binary DLT constants (matches lib/dlt/parser.py)
# ────────────────────────────────────────────────────────────────────────────
DLT_STORAGE_MAGIC = b"DLT\x01"
HTYP_EXT_HDR      = 0x01          # extended header present

# Verbose string argument type (TYPE_STRG | STRG_UTF8)
TYPE_STRG_UTF8 = 0x00008200

# Log levels  (mtin field in msin byte)
FATAL, ERROR, WARN, INFO, DEBUG, VERBOSE = 1, 2, 3, 4, 5, 6

# Message type (mstp): 0=log, 1=app_trace, 2=network_trace, 3=control
LOG = 0


# ────────────────────────────────────────────────────────────────────────────
# Low-level helpers
# ────────────────────────────────────────────────────────────────────────────

def _pad4(s: str) -> bytes:
    return s.encode("ascii", errors="replace").ljust(4, b"\x00")[:4]


def _string_arg(text: str) -> bytes:
    """Encode one verbose DLT string argument (type-info + len + data)."""
    data = text.encode("utf-8") + b"\x00"   # null-terminated
    return struct.pack("<IH", TYPE_STRG_UTF8, len(data)) + data


def make_message(
    ecu: str,
    app: str,
    ctx: str,
    level: int,
    text: str,
    seconds: int,
    useconds: int,
    counter: int,
) -> bytes:
    """Build a complete DLT storage-header message."""
    msin     = 0x01 | (level << 4)          # verbose=1, mstp=0 (log), mtin=level
    ext_hdr  = struct.pack("BB", msin, 1) + _pad4(app) + _pad4(ctx)
    payload  = _string_arg(text)
    msg_len  = 4 + len(ext_hdr) + len(payload)   # 4 = size of std header itself
    std_hdr  = struct.pack(">BBH", HTYP_EXT_HDR, counter & 0xFF, msg_len)
    stor_hdr = DLT_STORAGE_MAGIC + struct.pack(">Ii", seconds, useconds) + _pad4(ecu)
    return stor_hdr + std_hdr + ext_hdr + payload


# ────────────────────────────────────────────────────────────────────────────
# Message catalogue
# Each entry:  (ecu, app, ctx, level, payload_text)
# Ordered to tell a coherent story: vehicle ECU logs at a dealership / OTA update.
# ────────────────────────────────────────────────────────────────────────────

MESSAGES = [
    # ── System boot ─────────────────────────────────────────────────────────
    ("ECU1", "APPL", "BOOT", INFO,  "System boot: firmware v2.14.3 starting"),
    ("ECU1", "APPL", "BOOT", INFO,  "VIN WBA3A9C50EF478312 detected"),
    ("ECU1", "APPL", "BOOT", INFO,  "Owner registered: Max Mustermann, max.mustermann@bmw-dealer.de"),
    ("ECU1", "APPL", "BOOT", INFO,  "Dealer contact: service@autohaus-berlin.de, +49 30 88762100"),

    # ── User authentication ──────────────────────────────────────────────────
    ("ECU1", "AUTH", "SESS", INFO,  "Login attempt: user=alice.weber@gmail.com from IP 10.0.2.15"),
    ("ECU1", "AUTH", "SESS", INFO,  "Authentication successful for alice.weber@gmail.com"),
    ("ECU1", "AUTH", "SESS", WARN,  "Failed login attempt #2 for bob.schmidt@outlook.de"),
    ("ECU1", "AUTH", "SESS", ERROR, "Account locked after 3 failed attempts: frank.huber@yahoo.de"),
    ("ECU1", "AUTH", "SESS", INFO,  "Session token issued: user=alice.weber@gmail.com token_id=sess_4f9a1b2c"),

    # ── Navigation / GPS ────────────────────────────────────────────────────
    ("ECU2", "NAVM", "GPS",  INFO,  "Home address set: Kurfürstendamm 12, 10719 Berlin, Germany"),
    ("ECU2", "NAVM", "GPS",  INFO,  "GPS fix acquired: lat=52.520008 lon=13.404954 (Berlin city centre)"),
    ("ECU2", "NAVM", "GPS",  INFO,  "Route planned: start=52.520008,13.404954 end=48.137154,11.576124"),
    ("ECU2", "NAVM", "GPS",  DEBUG, "Waypoint saved: Hauptstrasse 45, 80336 München contact=+49 89 12345678"),
    ("ECU2", "NAVM", "GPS",  INFO,  "Work address saved: Friedrichstrasse 100, 10117 Berlin"),

    # ── Phone / Bluetooth pairing ────────────────────────────────────────────
    ("ECU1", "BTLE", "PAIR", INFO,  "Bluetooth device paired: name=Alice's iPhone 15 address=A4:B8:C2:D3:E4:F5"),
    ("ECU1", "BTLE", "PAIR", INFO,  "Phone number synced from contacts: +44 7911 654321 (James O'Brien)"),
    ("ECU1", "BTLE", "PAIR", INFO,  "WhatsApp notification from +49 170 9876543: Bitte ruf mich zurück"),
    ("ECU1", "BTLE", "PAIR", DEBUG, "Calendar sync: event='Doctor appointment Praxis Dr. Meier' at 2026-03-15 09:00"),

    # ── OTA update / remote management ──────────────────────────────────────
    ("ECU1", "OTAM", "HTTP", INFO,  "OTA update requested by user: alice.weber@gmail.com via app"),
    ("ECU1", "OTAM", "HTTP", INFO,  "Download URL: https://updates.vehicle-ota.example.com/fw/v2.15.0.bin?token=eyJhbGciOiJIUzI1NiJ9.eyJ1c2VyIjoiYWxpY2Uud2ViZXJAZ21haWwuY29tIn0.abc123"),
    ("ECU1", "OTAM", "HTTP", DEBUG, "Update server response: user_id=usr_99182 email=alice.weber@gmail.com plan=premium"),
    ("ECU1", "OTAM", "HTTP", WARN,  "Retry 1/3 connecting to 203.0.113.42:443 for user alice.weber@gmail.com"),

    # ── Vehicle diagnostics (DTC codes with owner context) ───────────────────
    ("ECU3", "DIAG", "DTC",  INFO,  "DTC P0300 logged for vehicle WBA3A9C50EF478312 owner=Max Mustermann"),
    ("ECU3", "DIAG", "DTC",  WARN,  "Emission fault detected: reporting to regulatory@kba.de for VIN WBA3A9C50EF478312"),
    ("ECU3", "DIAG", "DTC",  INFO,  "Remote diagnostic session opened by tech ID T-00412 (hans.gruber@workshop.de)"),

    # ── Payment / subscription ───────────────────────────────────────────────
    ("ECU1", "PMNT", "SUBS", INFO,  "Subscription renewal: alice.weber@gmail.com IBAN DE89 3704 0044 0532 0130 00"),
    ("ECU1", "PMNT", "SUBS", INFO,  "Payment confirmed: €49.99 charged to card ending 4242 for alice.weber@gmail.com"),
    ("ECU1", "PMNT", "SUBS", WARN,  "Payment failed: card expired for frank.huber@yahoo.de, retry scheduled"),

    # ── Emergency / crash data ───────────────────────────────────────────────
    ("ECU3", "EMER", "ECAL", ERROR, "eCall triggered: vehicle WBA3A9C50EF478312 at lat=52.4795,lon=13.3671"),
    ("ECU3", "EMER", "ECAL", INFO,  "Emergency contact notified: Lisa Mustermann +49 160 1112233"),
    ("ECU3", "EMER", "ECAL", INFO,  "Crash data transmitted to rescue@rettungsdienst-berlin.de"),

    # ── Miscellaneous / social handles ─────────────────────────────────────
    ("ECU1", "APPX", "NOTF", INFO,  "Twitter/X notification: @aliceweber123 mentioned you in a post"),
    ("ECU1", "APPX", "NOTF", INFO,  "Instagram message from @maxmustermann_official received"),
    ("ECU1", "APPX", "NOTF", DEBUG, "Calendar reminder: Birthday of Lena Müller on 1989-04-17 (she turns 37)"),

    # ── Network / telemetry ──────────────────────────────────────────────────
    ("ECU2", "NETW", "TELE", INFO,  "Telemetry endpoint: https://telemetry.oem-cloud.example.com/v3/ingest"),
    ("ECU2", "NETW", "TELE", DEBUG, "Sending driver profile id=DRV-7742 name=Max Mustermann dob=1985-06-23 to cloud"),
    ("ECU2", "NETW", "TELE", DEBUG, "Driver score uploaded: driver=Max Mustermann score=87 insurance=allianz@kfz.de"),

    # ── Clean messages (no PII – should pass cleanly) ────────────────────────
    ("ECU1", "APPL", "KERN", INFO,  "Kernel watchdog reset timer"),
    ("ECU1", "APPL", "KERN", DEBUG, "Memory usage: heap 42% stack 18%"),
    ("ECU2", "NAVM", "REND", INFO,  "Map tile cache cleared"),
    ("ECU3", "DIAG", "HLTH", INFO,  "CAN bus health check passed"),
    ("ECU1", "APPL", "KERN", DEBUG, "Dark mode toggled by user preference"),
    ("ECU1", "APPL", "KERN", INFO,  "Shutdown requested by ignition-off event"),
]


# ────────────────────────────────────────────────────────────────────────────
# Write binary .dlt file
# ────────────────────────────────────────────────────────────────────────────

def generate(output_path: str = "system.dlt"):
    base_seconds  = 1741478400   # 2026-03-09 00:00:00 UTC (approx)
    base_useconds = 0
    counter = 0

    with open(output_path, "wb") as fh:
        for i, (ecu, app, ctx, level, text) in enumerate(MESSAGES):
            seconds  = base_seconds + i * 2
            useconds = (i * 123456) % 1_000_000
            msg = make_message(ecu, app, ctx, level, text, seconds, useconds, counter)
            fh.write(msg)
            counter = (counter + 1) % 256

    print(f"Written {len(MESSAGES)} DLT messages to '{output_path}'")
    print(f"  Messages with PII: ~{len(MESSAGES) - 6}  (last 6 are clean)")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "system.dlt"
    generate(out)
