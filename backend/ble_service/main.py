"""
BLE Service for Diabetes MVP — AccuChek Instant Kit Integration.

This service communicates with AccuChek Instant glucometers via Bluetooth
Low Energy (BLE) using the Bleak library. It scans for devices advertising
the Glucose Service UUID, connects, reads glucose measurements from the
Glucose Measurement characteristic (0x2A18), parses the data per the
Bluetooth SIG specification, and stores readings in the shared SQLite
database.

The service runs as an async loop:
  Discover → Connect → Read → Store → Disconnect → Repeat

Usage:
    python -m ble_service.main

Environment variables (all optional, defaults shown):
    DIABETES_MVP_DB_PATH       — Path to SQLite database (./diabetes_mvp.db)
    DIABETES_MVP_SCAN_INTERVAL — Seconds between scans (30)
    DIABETES_MVP_SCAN_DURATION — Seconds per scan window (10)
    DIABETES_MVP_DEVICE_WHITELIST — Comma-separated BLE addresses (empty = all)
"""

import asyncio
import logging
import os
import signal
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

try:
    from bleak import BleakClient, BleakScanner
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
except ImportError:
    print(
        "ERROR: 'bleak' library is required. Install with: pip install bleak",
        file=sys.stderr,
    )
    sys.exit(1)

from ble_service.glucose_parser import GlucoseMeasurementParser

# ── Logging setup ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ble_service")

# ── BLE UUID constants ───────────────────────────────────────────────────────

GLUCOSE_SERVICE_UUID = "00001808-0000-1000-8000-00805f9b34fb"
GLUCOSE_MEASUREMENT_CHAR_UUID = "00002A18-0000-1000-8000-00805f9b34fb"
GLUCOSE_MEASUREMENT_CONTEXT_CHAR_UUID = "00002A34-0000-1000-8000-00805f9b34fb"
RECORD_ACCESS_CONTROL_POINT_CHAR_UUID = "00002A52-0000-1000-8000-00805f9b34fb"


# ── Configuration ────────────────────────────────────────────────────────────


class BLEServiceConfig:
    """Configuration for the BLE service.

    All values can be overridden via environment variables.

    Attributes:
        db_path: Path to the SQLite database file.
        scan_interval: Seconds between BLE scan cycles.
        scan_duration: Seconds for each active BLE scan window.
        device_whitelist: Set of allowed BLE addresses (empty = accept all).
        max_reconnect_delay: Maximum seconds for exponential backoff.
    """

    def __init__(self) -> None:
        self.db_path: str = os.environ.get(
            "DIABETES_MVP_DB_PATH",
            str(Path(__file__).resolve().parent.parent / "diabetes_mvp.db"),
        )
        self.scan_interval: int = int(
            os.environ.get("DIABETES_MVP_SCAN_INTERVAL", "30")
        )
        self.scan_duration: int = int(
            os.environ.get("DIABETES_MVP_SCAN_DURATION", "10")
        )
        self.max_reconnect_delay: int = 60

        # Parse device whitelist from comma-separated BLE addresses
        whitelist_str = os.environ.get("DIABETES_MVP_DEVICE_WHITELIST", "")
        if whitelist_str.strip():
            self.device_whitelist: set[str] = {
                addr.strip().upper() for addr in whitelist_str.split(",") if addr.strip()
            }
        else:
            self.device_whitelist = set()

    def __repr__(self) -> str:
        return (
            f"BLEServiceConfig(db_path={self.db_path!r}, "
            f"scan_interval={self.scan_interval}, "
            f"scan_duration={self.scan_duration}, "
            f"whitelist={self.device_whitelist}, "
            f"max_reconnect_delay={self.max_reconnect_delay})"
        )


# ── Device connection state ──────────────────────────────────────────────────


class DeviceState:
    """Track per-device connection state and backoff timing.

    Attributes:
        address: The BLE MAC address of the device.
        name: The advertised device name (if available).
        connected: Whether we currently have an active connection.
        reconnect_delay: Current exponential backoff delay in seconds.
        last_reading_seq: Last sequence number read from this device.
        last_seen: Timestamp when the device was last discovered.
        consecutive_failures: Number of consecutive connection/read failures.
    """

    def __init__(self, address: str, name: Optional[str] = None) -> None:
        self.address = address
        self.name = name or "Unknown"
        self.connected: bool = False
        self.reconnect_delay: float = 1.0
        self.last_reading_seq: Optional[int] = None
        self.last_seen: datetime = datetime.now(timezone.utc)
        self.consecutive_failures: int = 0

    def record_success(self) -> None:
        """Reset backoff after a successful operation."""
        self.reconnect_delay = 1.0
        self.consecutive_failures = 0

    def record_failure(self, max_delay: float) -> None:
        """Increase backoff after a failure, up to max_delay."""
        self.consecutive_failures += 1
        self.reconnect_delay = min(self.reconnect_delay * 2, max_delay)

    def __repr__(self) -> str:
        return (
            f"DeviceState({self.address}, name={self.name!r}, "
            f"connected={self.connected}, delay={self.reconnect_delay}s, "
            f"failures={self.consecutive_failures})"
        )


# ── Database helpers ─────────────────────────────────────────────────────────

# SQL to create tables if they don't exist (matching the FastAPI app schema)
_CREATE_DEVICES_TABLE = """
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER,
    device_name VARCHAR DEFAULT 'AccuChek Instant',
    ble_address VARCHAR UNIQUE NOT NULL,
    is_paired BOOLEAN DEFAULT 0,
    last_sync_at DATETIME,
    status VARCHAR DEFAULT 'disconnected',
    battery_level INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE SET NULL
);
"""

_CREATE_GLUCOSE_READINGS_TABLE = """
CREATE TABLE IF NOT EXISTS glucose_readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    glucose_mg_dl FLOAT NOT NULL,
    measurement_timestamp DATETIME NOT NULL,
    sequence_number INTEGER,
    source_device VARCHAR DEFAULT 'AccuChek Instant',
    context VARCHAR,
    is_synced BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES patients(id) ON DELETE CASCADE
);
"""

_CREATE_READINGS_INDEX = """
CREATE INDEX IF NOT EXISTS ix_glucose_readings_patient_id
ON glucose_readings (patient_id);
"""

_CREATE_PATIENTS_TABLE = """
CREATE TABLE IF NOT EXISTS patients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name VARCHAR NOT NULL,
    last_name VARCHAR NOT NULL,
    date_of_birth DATE NOT NULL,
    gender VARCHAR NOT NULL,
    phone VARCHAR,
    address TEXT,
    emergency_contact VARCHAR,
    family_diabetes_history BOOLEAN DEFAULT 0,
    hypertension_history BOOLEAN DEFAULT 0,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_db(db_path: str) -> aiosqlite.Connection:
    """Initialize the SQLite database and return an async connection.

    Creates the patients, devices, and glucose_readings tables if they
    don't exist, ensuring compatibility with the FastAPI application's
    SQLAlchemy schema. The patients table is included so the BLE service
    can run standalone for testing purposes.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        An open aiosqlite connection.
    """
    db = await aiosqlite.connect(db_path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL;")
    await db.execute("PRAGMA foreign_keys=ON;")
    await db.execute(_CREATE_PATIENTS_TABLE)
    await db.execute(_CREATE_DEVICES_TABLE)
    await db.execute(_CREATE_GLUCOSE_READINGS_TABLE)
    await db.execute(_CREATE_READINGS_INDEX)
    await db.commit()
    logger.info("Database initialized at %s", db_path)
    return db


async def store_glucose_reading(
    db: aiosqlite.Connection,
    patient_id: int,
    glucose_mg_dl: float,
    measurement_timestamp: datetime,
    sequence_number: Optional[int],
    source_device: str = "AccuChek Instant",
    context: Optional[str] = None,
) -> int:
    """Insert a glucose reading into the database.

    Args:
        db: Active aiosqlite connection.
        patient_id: The ID of the patient this reading belongs to.
        glucose_mg_dl: Glucose concentration in mg/dL.
        measurement_timestamp: When the measurement was taken.
        sequence_number: BLE sequence number from the glucometer.
        source_device: Name of the source device.
        context: Measurement context (fasting, postprandial, etc.).

    Returns:
        The ID of the inserted row.
    """
    ts_str = measurement_timestamp.strftime("%Y-%m-%d %H:%M:%S")
    cursor = await db.execute(
        """
        INSERT INTO glucose_readings
            (patient_id, glucose_mg_dl, measurement_timestamp,
             sequence_number, source_device, context, is_synced)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (patient_id, glucose_mg_dl, ts_str, sequence_number, source_device, context),
    )
    await db.commit()
    reading_id = cursor.lastrowid
    logger.info(
        "Stored glucose reading id=%d: patient=%d, %.1f mg/dL at %s, seq=%s",
        reading_id,
        patient_id,
        glucose_mg_dl,
        ts_str,
        sequence_number,
    )
    return reading_id  # type: ignore[return-value]


async def update_device_status(
    db: aiosqlite.Connection,
    ble_address: str,
    status: str,
    last_sync_at: Optional[datetime] = None,
) -> None:
    """Update the status of a BLE device in the database.

    If the device does not exist in the database, it will be inserted
    as an unpaired device with the given status.

    Args:
        db: Active aiosqlite connection.
        ble_address: The BLE MAC address of the device.
        status: New status string (disconnected, connected, syncing, error).
        last_sync_at: Timestamp of the last successful sync, if applicable.
    """
    # Check if the device already exists
    cursor = await db.execute(
        "SELECT id FROM devices WHERE ble_address = ?",
        (ble_address,),
    )
    row = await cursor.fetchone()

    if row is not None:
        # Update existing device
        if last_sync_at is not None:
            sync_str = last_sync_at.strftime("%Y-%m-%d %H:%M:%S")
            await db.execute(
                """
                UPDATE devices SET status = ?, last_sync_at = ?
                WHERE ble_address = ?
                """,
                (status, sync_str, ble_address),
            )
        else:
            await db.execute(
                "UPDATE devices SET status = ? WHERE ble_address = ?",
                (status, ble_address),
            )
    else:
        # Insert new device (unpaired, no patient assigned yet)
        sync_str = (
            last_sync_at.strftime("%Y-%m-%d %H:%M:%S")
            if last_sync_at is not None
            else None
        )
        await db.execute(
            """
            INSERT INTO devices
                (device_name, ble_address, is_paired, last_sync_at, status)
            VALUES ('AccuChek Instant', ?, 0, ?, ?)
            """,
            (ble_address, sync_str, status),
        )

    await db.commit()
    logger.debug("Device %s status updated to: %s", ble_address, status)


async def get_patient_for_device(
    db: aiosqlite.Connection,
    ble_address: str,
) -> Optional[int]:
    """Look up the patient ID associated with a BLE device address.

    Args:
        db: Active aiosqlite connection.
        ble_address: The BLE MAC address of the device.

    Returns:
        The patient_id if the device is paired, or None.
    """
    cursor = await db.execute(
        "SELECT patient_id FROM devices WHERE ble_address = ? AND is_paired = 1",
        (ble_address,),
    )
    row = await cursor.fetchone()
    if row is not None:
        return row["patient_id"]
    return None


async def get_last_sequence_for_device(
    db: aiosqlite.Connection,
    ble_address: str,
) -> Optional[int]:
    """Look up the last stored sequence number for a device.

    This helps avoid storing duplicate readings when re-reading
    the same records from a glucometer.

    Args:
        db: Active aiosqlite connection.
        ble_address: The BLE MAC address of the device.

    Returns:
        The last sequence number stored, or None if no readings exist.
    """
    cursor = await db.execute(
        """
        SELECT gr.sequence_number
        FROM glucose_readings gr
        JOIN devices d ON d.patient_id = gr.patient_id
        WHERE d.ble_address = ?
        ORDER BY gr.sequence_number DESC
        LIMIT 1
        """,
        (ble_address,),
    )
    row = await cursor.fetchone()
    if row is not None and row["sequence_number"] is not None:
        return row["sequence_number"]
    return None


# ── BLE notification handler ────────────────────────────────────────────────


class GlucoseNotificationHandler:
    """Handle BLE notifications from the Glucose Measurement characteristic.

    When subscribed to indications/notifications on 0x2A18, the glucometer
    sends one notification per stored reading. This handler collects them
    and signals completion via an asyncio Event.
    """

    def __init__(
        self,
        device_address: str,
        db: aiosqlite.Connection,
        patient_id: int,
        last_known_seq: Optional[int],
    ) -> None:
        self.device_address = device_address
        self.db = db
        self.patient_id = patient_id
        self.last_known_seq = last_known_seq
        self.readings: list[dict] = []
        self.new_count: int = 0
        self.done_event = asyncio.Event()
        self._parser = GlucoseMeasurementParser()

    def handle_notification(self, sender: int, data: bytearray) -> None:
        """Callback for BLE notifications on the Glucose Measurement characteristic.

        Args:
            sender: The handle of the characteristic sending the notification.
            data: The raw bytes of the notification payload.
        """
        try:
            parsed = self._parser.parse(bytes(data))
            self.readings.append(parsed)

            # Only count as new if sequence number is greater than last known
            seq = parsed.get("sequence_number")
            glucose = parsed.get("glucose_mg_dl")

            if glucose is not None:
                if self.last_known_seq is None or (seq is not None and seq > self.last_known_seq):
                    self.new_count += 1
                    logger.info(
                        "New glucose reading from %s: seq=%d, %.1f mg/dL",
                        self.device_address,
                        seq or 0,
                        glucose,
                    )
                else:
                    logger.debug(
                        "Skipping duplicate reading from %s: seq=%d (last=%s)",
                        self.device_address,
                        seq or 0,
                        self.last_known_seq,
                    )

        except ValueError as exc:
            logger.error(
                "Failed to parse glucose notification from %s: %s — raw=%s",
                self.device_address,
                exc,
                data.hex(),
            )

    async def store_new_readings(self) -> int:
        """Store all new (non-duplicate) readings into the database.

        Returns:
            The number of readings actually stored.
        """
        stored = 0
        for reading in self.readings:
            seq = reading.get("sequence_number")
            glucose = reading.get("glucose_mg_dl")

            if glucose is None:
                logger.warning(
                    "Skipping reading with no glucose value: seq=%s", seq
                )
                continue

            # Skip if we've already stored this sequence number
            if self.last_known_seq is not None and seq is not None and seq <= self.last_known_seq:
                continue

            # Determine context from sample type if available
            context = None
            sample_type = reading.get("sample_type")
            if sample_type and sample_type not in ("Reserved", "Unknown"):
                context = sample_type

            await store_glucose_reading(
                db=self.db,
                patient_id=self.patient_id,
                glucose_mg_dl=glucose,
                measurement_timestamp=reading["timestamp"],
                sequence_number=seq,
                source_device="AccuChek Instant",
                context=context,
            )
            stored += 1

        return stored


# ── Main BLE Service ────────────────────────────────────────────────────────


class BLEService:
    """Async BLE service that discovers, connects to, and reads from
    AccuChek Instant glucometers.

    The service runs a continuous loop:
      1. Scan for BLE devices advertising the Glucose Service UUID.
      2. For each discovered device (optionally filtered by whitelist):
         a. Connect via Bleak.
         b. Subscribe to Glucose Measurement indications.
         c. Use Record Access Control Point (RACP) to request stored records.
         d. Parse and store each reading.
         e. Disconnect.
      3. Wait for the configured scan interval, then repeat.

    Supports graceful shutdown via signal handlers (SIGINT, SIGTERM).
    Handles disconnections with exponential backoff per device.
    """

    def __init__(self, config: Optional[BLEServiceConfig] = None) -> None:
        self.config = config or BLEServiceConfig()
        self._device_states: dict[str, DeviceState] = {}
        self._db: Optional[aiosqlite.Connection] = None
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._active_connections: dict[str, BleakClient] = {}

    async def start(self) -> None:
        """Start the BLE service main loop.

        Initializes the database, registers signal handlers, and enters
        the scan/connect/read cycle until shutdown is requested.
        """
        logger.info("Starting BLE service with config: %s", self.config)
        self._running = True

        # Initialize database
        self._db = await init_db(self.config.db_path)

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._request_shutdown)

        try:
            while self._running:
                try:
                    await self._scan_and_process_cycle()
                except Exception as exc:
                    logger.error("Error in scan cycle: %s", exc, exc_info=True)

                if self._running:
                    # Wait for next scan cycle or shutdown
                    try:
                        await asyncio.wait_for(
                            self._shutdown_event.wait(),
                            timeout=self.config.scan_interval,
                        )
                        # If we get here, shutdown was requested
                        break
                    except asyncio.TimeoutError:
                        pass  # Normal: scan interval elapsed
        finally:
            await self._cleanup()

    def _request_shutdown(self) -> None:
        """Signal handler to request graceful shutdown."""
        logger.info("Shutdown signal received, stopping BLE service...")
        self._running = False
        self._shutdown_event.set()

    async def _cleanup(self) -> None:
        """Clean up resources: disconnect all devices, close database."""
        logger.info("Cleaning up BLE service...")

        # Disconnect active BLE clients
        for address, client in self._active_connections.items():
            try:
                if client.is_connected:
                    await client.disconnect()
                    logger.info("Disconnected from %s", address)
            except Exception as exc:
                logger.warning("Error disconnecting from %s: %s", address, exc)
        self._active_connections.clear()

        # Update all device statuses to disconnected
        if self._db is not None:
            for address in self._device_states:
                try:
                    await update_device_status(self._db, address, "disconnected")
                except Exception as exc:
                    logger.warning(
                        "Error updating device status for %s: %s", address, exc
                    )
            await self._db.close()
            logger.info("Database connection closed")

        logger.info("BLE service stopped")

    async def _scan_and_process_cycle(self) -> None:
        """Execute one full scan and process cycle.

        Scans for AccuChek devices, then connects and reads from each
        discovered device that is in the whitelist (or all if no whitelist).
        """
        logger.info(
            "Starting BLE scan (duration=%ds)...", self.config.scan_duration
        )

        discovered = await self._scan_for_devices()

        if not discovered:
            logger.info("No AccuChek devices found in this scan cycle")
            return

        logger.info(
            "Discovered %d AccuChek device(s): %s",
            len(discovered),
            [d.address for d in discovered],
        )

        # Process each discovered device
        for device in discovered:
            if not self._running:
                break

            # Apply whitelist filter
            if self.config.device_whitelist and device.address.upper() not in self.config.device_whitelist:
                logger.debug(
                    "Skipping device %s (not in whitelist)", device.address
                )
                continue

            await self._process_device(device)

    async def _scan_for_devices(self) -> list[BLEDevice]:
        """Scan for BLE devices advertising the Glucose Service UUID.

        Uses BleakScanner with a service UUID filter to find AccuChek
        Instant glucometers. The scan runs for the configured duration.

        Returns:
            A list of discovered BLEDevice objects.
        """
        discovered_devices: list[BLEDevice] = []

        def detection_callback(
            device: BLEDevice, advertisement_data: AdvertisementData
        ) -> None:
            """Called when a BLE device is detected during scanning."""
            # Check if the device advertises the Glucose Service UUID
            service_uuids = advertisement_data.service_uuids or []
            if GLUCOSE_SERVICE_UUID.lower() in [u.lower() for u in service_uuids]:
                logger.info(
                    "Found Glucose Service device: %s (%s) RSSI=%d",
                    device.address,
                    device.name or "Unknown",
                    advertisement_data.rssi or 0,
                )
                discovered_devices.append(device)

                # Update device state
                if device.address not in self._device_states:
                    self._device_states[device.address] = DeviceState(
                        address=device.address,
                        name=device.name,
                    )
                self._device_states[device.address].last_seen = datetime.now(
                    timezone.utc
                )
                self._device_states[device.address].name = device.name or "Unknown"

        try:
            scanner = BleakScanner(
                detection_callback=detection_callback,
                service_uuids=[GLUCOSE_SERVICE_UUID],
                scanning_mode="active",
            )

            await scanner.start()
            await asyncio.sleep(self.config.scan_duration)
            await scanner.stop()

        except Exception as exc:
            logger.error("BLE scan failed: %s", exc, exc_info=True)

        return discovered_devices

    async def _process_device(self, device: BLEDevice) -> None:
        """Connect to a discovered device and read glucose measurements.

        Handles the full lifecycle: connect → read → store → disconnect.
        Applies exponential backoff on failures.

        Args:
            device: The BLE device to process.
        """
        state = self._device_states.get(device.address)
        if state is None:
            state = DeviceState(address=device.address, name=device.name)
            self._device_states[device.address] = state

        # If already connected, skip
        if state.connected:
            logger.debug("Already connected to %s, skipping", device.address)
            return

        # Apply backoff delay if we've had recent failures
        if state.consecutive_failures > 0:
            delay = state.reconnect_delay
            logger.info(
                "Backing off %s for %.1fs (%d consecutive failures)",
                device.address,
                delay,
                state.consecutive_failures,
            )
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=delay
                )
                return  # Shutdown requested during backoff
            except asyncio.TimeoutError:
                pass  # Backoff completed

        logger.info("Connecting to %s (%s)...", device.address, state.name)

        client = BleakClient(
            device,
            disconnected_callback=lambda c: self._on_disconnected(
                device.address, c
            ),
            timeout=15.0,
        )

        try:
            await client.connect()
            state.connected = True
            self._active_connections[device.address] = client
            logger.info("Connected to %s", device.address)

            if self._db is not None:
                await update_device_status(
                    self._db, device.address, "connected"
                )

            # Read glucose measurements
            await self._read_glucose_measurements(client, device.address)

            # Record success and update state
            state.record_success()
            if self._db is not None:
                await update_device_status(
                    self._db,
                    device.address,
                    "connected",
                    last_sync_at=datetime.now(timezone.utc),
                )

        except Exception as exc:
            logger.error(
                "Error processing device %s: %s",
                device.address,
                exc,
                exc_info=True,
            )
            state.record_failure(self.config.max_reconnect_delay)
            if self._db is not None:
                await update_device_status(self._db, device.address, "error")

        finally:
            # Disconnect
            try:
                if client.is_connected:
                    await client.disconnect()
            except Exception as exc:
                logger.warning(
                    "Error disconnecting from %s: %s", device.address, exc
                )
            finally:
                state.connected = False
                self._active_connections.pop(device.address, None)
                if self._db is not None:
                    await update_device_status(
                        self._db, device.address, "disconnected"
                    )

    def _on_disconnected(self, address: str, client: BleakClient) -> None:
        """Callback when a BLE device disconnects unexpectedly.

        Args:
            address: The BLE address of the disconnected device.
            client: The BleakClient that was disconnected.
        """
        logger.warning("Device %s disconnected unexpectedly", address)
        state = self._device_states.get(address)
        if state is not None:
            state.connected = False
            state.record_failure(self.config.max_reconnect_delay)
        self._active_connections.pop(address, None)

    async def _read_glucose_measurements(
        self, client: BleakClient, device_address: str
    ) -> None:
        """Read glucose measurements from a connected glucometer.

        First attempts to subscribe to indications on the Glucose Measurement
        characteristic and request stored records via RACP. Falls back to
        a direct read of the characteristic if subscription fails.

        Args:
            client: A connected BleakClient.
            device_address: The BLE address (for logging/DB purposes).
        """
        if self._db is None:
            logger.error("Database not initialized, cannot store readings")
            return

        # Look up the patient ID for this device
        patient_id = await get_patient_for_device(self._db, device_address)
        if patient_id is None:
            logger.warning(
                "Device %s is not paired with any patient; "
                "readings will not be stored. Pair the device first "
                "via the API (POST /api/devices/pair).",
                device_address,
            )
            return

        # Get the last known sequence number to avoid duplicates
        last_known_seq = await get_last_sequence_for_device(
            self._db, device_address
        )

        # Update device status to syncing
        await update_device_status(self._db, device_address, "syncing")

        # Try notification-based reading first (preferred for AccuChek)
        try:
            await self._read_via_notifications(
                client, device_address, patient_id, last_known_seq
            )
            return
        except Exception as exc:
            logger.warning(
                "Notification-based reading failed for %s: %s; "
                "falling back to direct read",
                device_address,
                exc,
            )

        # Fallback: direct read of the characteristic
        try:
            await self._read_direct(
                client, device_address, patient_id, last_known_seq
            )
        except Exception as exc:
            logger.error(
                "Direct read also failed for %s: %s",
                device_address,
                exc,
                exc_info=True,
            )
            raise

    async def _read_via_notifications(
        self,
        client: BleakClient,
        device_address: str,
        patient_id: int,
        last_known_seq: Optional[int],
    ) -> None:
        """Read glucose measurements via BLE indications/notifications.

        Subscribes to the Glucose Measurement characteristic and uses
        the Record Access Control Point (RACP) to request all stored
        records from the glucometer.

        Args:
            client: A connected BleakClient.
            device_address: BLE address of the device.
            patient_id: The patient ID to associate readings with.
            last_known_seq: Last sequence number already stored.
        """
        handler = GlucoseNotificationHandler(
            device_address=device_address,
            db=self._db,  # type: ignore[arg-type]
            patient_id=patient_id,
            last_known_seq=last_known_seq,
        )

        # Subscribe to indications on the Glucose Measurement characteristic
        await client.start_notify(
            GLUCOSE_MEASUREMENT_CHAR_UUID,
            handler.handle_notification,
        )
        logger.debug(
            "Subscribed to glucose measurement indications on %s",
            device_address,
        )

        try:
            # Request all stored records via RACP
            # RACP opcode: 0x01 = Report Stored Records
            # RACP operator: 0x01 = All records
            racp_request = bytes([0x01, 0x01])
            try:
                await client.write_gatt_char(
                    RECORD_ACCESS_CONTROL_POINT_CHAR_UUID,
                    racp_request,
                    response=True,
                )
                logger.debug(
                    "Sent RACP 'Report All Records' request to %s",
                    device_address,
                )
            except Exception as exc:
                logger.warning(
                    "RACP write failed for %s: %s; "
                    "trying to read without RACP",
                    device_address,
                    exc,
                )
                # If RACP fails, try reading the characteristic directly
                raw_data = await client.read_gatt_char(
                    GLUCOSE_MEASUREMENT_CHAR_UUID
                )
                if raw_data:
                    handler.handle_notification(0, bytearray(raw_data))

            # Wait for all notifications to arrive
            # The glucometer sends them rapidly; give it time
            await asyncio.sleep(3.0)

            # Stop notifications
            try:
                await client.stop_notify(GLUCOSE_MEASUREMENT_CHAR_UUID)
            except Exception as exc:
                logger.warning(
                    "Error stopping notifications on %s: %s",
                    device_address,
                    exc,
                )

            # Store new readings
            stored = await handler.store_new_readings()
            logger.info(
                "Stored %d new reading(s) from %s (total received: %d)",
                stored,
                device_address,
                len(handler.readings),
            )

        except Exception:
            # Ensure we try to stop notifications even on error
            try:
                await client.stop_notify(GLUCOSE_MEASUREMENT_CHAR_UUID)
            except Exception:
                pass
            raise

    async def _read_direct(
        self,
        client: BleakClient,
        device_address: str,
        patient_id: int,
        last_known_seq: Optional[int],
    ) -> None:
        """Read a single glucose measurement directly from the characteristic.

        This is a fallback when notification-based reading fails. It reads
        a single record from the Glucose Measurement characteristic.

        Args:
            client: A connected BleakClient.
            device_address: BLE address of the device.
            patient_id: The patient ID to associate readings with.
            last_known_seq: Last sequence number already stored.
        """
        raw_data = await client.read_gatt_char(GLUCOSE_MEASUREMENT_CHAR_UUID)

        if not raw_data:
            logger.info("No data in glucose measurement characteristic for %s", device_address)
            return

        logger.debug(
            "Raw glucose data from %s (%d bytes): %s",
            device_address,
            len(raw_data),
            raw_data.hex(),
        )

        parser = GlucoseMeasurementParser()
        parsed = parser.parse(raw_data)

        glucose = parsed.get("glucose_mg_dl")
        if glucose is None:
            logger.warning("No glucose value in reading from %s", device_address)
            return

        # Check for duplicate
        seq = parsed.get("sequence_number")
        if last_known_seq is not None and seq is not None and seq <= last_known_seq:
            logger.info(
                "Skipping duplicate reading from %s: seq=%d <= last=%d",
                device_address,
                seq,
                last_known_seq,
            )
            return

        # Determine context
        context = None
        sample_type = parsed.get("sample_type")
        if sample_type and sample_type not in ("Reserved", "Unknown"):
            context = sample_type

        await store_glucose_reading(
            db=self._db,  # type: ignore[arg-type]
            patient_id=patient_id,
            glucose_mg_dl=glucose,
            measurement_timestamp=parsed["timestamp"],
            sequence_number=seq,
            source_device="AccuChek Instant",
            context=context,
        )

        # Also try to read Glucose Measurement Context if available
        try:
            context_data = await client.read_gatt_char(
                GLUCOSE_MEASUREMENT_CONTEXT_CHAR_UUID
            )
            if context_data:
                logger.debug(
                    "Glucose Measurement Context from %s: %s",
                    device_address,
                    context_data.hex(),
                )
                # Context parsing could be added here in the future
        except Exception as exc:
            logger.debug(
                "Glucose Measurement Context not available for %s: %s",
                device_address,
                exc,
            )


# ── Entry point ──────────────────────────────────────────────────────────────


async def run_service() -> None:
    """Create and run the BLE service as a standalone async application."""
    config = BLEServiceConfig()
    service = BLEService(config)
    await service.start()


def main() -> None:
    """Entry point for running the BLE service standalone.

    Usage:
        python -m ble_service.main
    """
    logger.info("=" * 60)
    logger.info("Diabetes MVP — BLE Service for AccuChek Instant")
    logger.info("=" * 60)

    try:
        asyncio.run(run_service())
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as exc:
        logger.critical("BLE service crashed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()