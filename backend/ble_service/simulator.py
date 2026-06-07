"""
BLE Simulator for Diabetes MVP — Development & Testing Without Hardware.

This module generates synthetic glucose readings that simulate the behavior
of an AccuChek Instant glucometer communicating over BLE. It stores the
readings in the same SQLite database used by the real BLE service, enabling
end-to-end testing of the full data pipeline without requiring physical
hardware.

Features:
- Generates realistic glucose readings at configurable intervals
- Simulates device discovery, connection, and data transfer lifecycle
- Supports multiple patients with independent glucose patterns
- Configurable glucose ranges, variability, and reading frequency
- Generates readings that follow realistic diurnal patterns
- Can produce both normal and abnormal readings for alert testing
- Uses the same GlucoseMeasurementParser to encode data, then parses
  it back, verifying the round-trip encoder/parser integrity

Usage:
    python -m ble_service.simulator

Environment variables (all optional, defaults shown):
    DIABETES_MVP_DB_PATH           — Path to SQLite database (./diabetes_mvp.db)
    DIABETES_MVP_SIM_PATIENTS      — Number of simulated patients (3)
    DIABETES_MVP_SIM_READINGS_DAY  — Readings per patient per day (4)
    DIABETES_MVP_SIM_DAYS_HISTORY  — Days of historical data to generate (7)
    DIABETES_MVP_SIM_INTERVAL      — Seconds between new readings (300)
    DIABETES_MVP_SIM_GLUCOSE_LOW   — Minimum glucose mg/dL (70)
    DIABETES_MVP_SIM_GLUCOSE_HIGH  — Maximum glucose mg/dL (180)
"""

import asyncio
import logging
import math
import os
import random
import signal
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiosqlite

from ble_service.glucose_parser import GlucoseMeasurementParser

# ── Logging setup ────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ble_simulator")


# ── Configuration ────────────────────────────────────────────────────────────


class SimulatorConfig:
    """Configuration for the BLE simulator.

    All values can be overridden via environment variables.

    Attributes:
        db_path: Path to the SQLite database file.
        num_patients: Number of simulated patients to create.
        readings_per_day: Glucose readings per patient per day.
        days_history: Days of historical data to pre-generate.
        interval_seconds: Seconds between generating new real-time readings.
        glucose_low: Lower bound for glucose values (mg/dL).
        glucose_high: Upper bound for normal glucose values (mg/dL).
    """

    def __init__(self) -> None:
        self.db_path: str = os.environ.get(
            "DIABETES_MVP_DB_PATH",
            str(Path(__file__).resolve().parent.parent / "diabetes_mvp.db"),
        )
        self.num_patients: int = int(
            os.environ.get("DIABETES_MVP_SIM_PATIENTS", "3")
        )
        self.readings_per_day: int = int(
            os.environ.get("DIABETES_MVP_SIM_READINGS_DAY", "4")
        )
        self.days_history: int = int(
            os.environ.get("DIABETES_MVP_SIM_DAYS_HISTORY", "7")
        )
        self.interval_seconds: int = int(
            os.environ.get("DIABETES_MVP_SIM_INTERVAL", "300")
        )
        self.glucose_low: int = int(
            os.environ.get("DIABETES_MVP_SIM_GLUCOSE_LOW", "70")
        )
        self.glucose_high: int = int(
            os.environ.get("DIABETES_MVP_SIM_GLUCOSE_HIGH", "180")
        )

    def __repr__(self) -> str:
        return (
            f"SimulatorConfig(patients={self.num_patients}, "
            f"readings/day={self.readings_per_day}, "
            f"history={self.days_history}d, "
            f"interval={self.interval_seconds}s, "
            f"range=[{self.glucose_low}-{self.glucose_high}] mg/dL)"
        )


# ── SQL for table creation (shared with main BLE service) ───────────────────

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


# ── Simulated patient data ──────────────────────────────────────────────────

FIRST_NAMES = [
    "Maria", "Jose", "Ana", "Carlos", "Elena",
    "Miguel", "Carmen", "Antonio", "Isabel", "Francisco",
    "Rosa", "David", "Pilar", "Juan", "Teresa",
]

LAST_NAMES = [
    "Garcia", "Rodriguez", "Martinez", "Lopez", "Sanchez",
    "Ramirez", "Torres", "Flores", "Rivera", "Gonzalez",
    "Hernandez", "Diaz", "Morales", "Jimenez", "Alvarez",
]


class SimulatedPatient:
    """Represents a simulated patient with associated glucose data.

    Attributes:
        patient_id: Database ID of the patient.
        first_name: Patient's first name.
        last_name: Patient's last name.
        ble_address: Simulated BLE MAC address.
        device_id: Database ID of the paired device.
        baseline_glucose: Baseline glucose level for this patient.
        glucose_variance: How much the glucose varies around baseline.
        is_diabetic: Whether the patient has elevated glucose patterns.
        last_sequence: Last sequence number generated.
    """

    def __init__(
        self,
        patient_id: int,
        first_name: str,
        last_name: str,
        ble_address: str,
        device_id: int,
        baseline_glucose: float = 120.0,
        glucose_variance: float = 30.0,
        is_diabetic: bool = False,
    ) -> None:
        self.patient_id = patient_id
        self.first_name = first_name
        self.last_name = last_name
        self.ble_address = ble_address
        self.device_id = device_id
        self.baseline_glucose = baseline_glucose
        self.glucose_variance = glucose_variance
        self.is_diabetic = is_diabetic
        self.last_sequence: int = 0

    def generate_glucose_reading(
        self, timestamp: datetime, context: Optional[str] = None
    ) -> dict:
        """Generate a realistic glucose reading for this patient.

        Simulates diurnal variation in glucose levels:
        - Early morning (dawn phenomenon): slightly elevated
        - Post-breakfast: elevated
        - Afternoon: moderate
        - Post-dinner: elevated
        - Night: lower

        Args:
            timestamp: When the reading was taken.
            context: Optional measurement context (fasting, postprandial, etc.).

        Returns:
            A dictionary with glucose_mg_dl, timestamp, and metadata.
        """
        hour = timestamp.hour

        # Diurnal pattern: add time-of-day effect
        if 4 <= hour < 8:
            # Dawn phenomenon: glucose tends to rise before waking
            time_offset = 15.0
        elif 8 <= hour < 11:
            # Post-breakfast peak
            time_offset = 35.0
        elif 11 <= hour < 14:
            # Late morning / pre-lunch
            time_offset = 10.0
        elif 14 <= hour < 17:
            # Post-lunch
            time_offset = 25.0
        elif 17 <= hour < 20:
            # Post-dinner
            time_offset = 30.0
        else:
            # Night: lower glucose
            time_offset = -10.0

        # Context-specific adjustments
        if context == "fasting":
            time_offset -= 15.0
        elif context == "postprandial":
            time_offset += 20.0

        # Diabetic patients have higher baseline and more variance
        if self.is_diabetic:
            base = self.baseline_glucose + 50.0
            variance = self.glucose_variance * 1.5
        else:
            base = self.baseline_glucose
            variance = self.glucose_variance

        # Generate reading with normal distribution around adjusted baseline
        raw_glucose = random.gauss(base + time_offset, variance)

        # Clamp to physiological range (20-600 mg/dL)
        glucose_mg_dl = max(20.0, min(600.0, round(raw_glucose, 1)))

        self.last_sequence += 1

        return {
            "glucose_mg_dl": glucose_mg_dl,
            "timestamp": timestamp,
            "sequence_number": self.last_sequence,
            "context": context,
            "patient_id": self.patient_id,
            "source_device": "AccuChek Instant (Simulated)",
        }


# ── Main Simulator Class ────────────────────────────────────────────────────


class BLESimulator:
    """BLE device simulator for development and testing.

    Generates synthetic glucose readings for multiple simulated patients,
    stores them in the shared SQLite database, and provides a continuous
    stream of new readings at configurable intervals.

    The simulator:
    1. Initializes the database schema (creates tables if needed).
    2. Creates simulated patients and devices if they don't exist.
    3. Generates historical readings for each patient.
    4. Enters a loop generating new readings at the configured interval.
    5. Encodes each reading through the GlucoseMeasurementParser to
       verify round-trip encoder/parser integrity.
    """

    def __init__(self, config: Optional[SimulatorConfig] = None) -> None:
        self.config = config or SimulatorConfig()
        self._db: Optional[aiosqlite.Connection] = None
        self._patients: list[SimulatedPatient] = []
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._parser = GlucoseMeasurementParser()

    async def start(self) -> None:
        """Start the simulator: initialize DB, create patients, generate data."""
        logger.info("Starting BLE Simulator with config: %s", self.config)
        self._running = True

        # Register signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._request_shutdown)

        # Initialize database
        self._db = await self._init_db()

        # Create simulated patients and devices
        await self._create_simulated_patients()

        # Generate historical readings
        await self._generate_historical_data()

        # Enter real-time simulation loop
        await self._realtime_loop()

    def _request_shutdown(self) -> None:
        """Signal handler to request graceful shutdown."""
        logger.info("Shutdown signal received, stopping simulator...")
        self._running = False
        self._shutdown_event.set()

    async def _init_db(self) -> aiosqlite.Connection:
        """Initialize the SQLite database and return an async connection.

        Returns:
            An open aiosqlite connection with WAL mode enabled.
        """
        db = await aiosqlite.connect(self.config.db_path)
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.executescript(_CREATE_PATIENTS_TABLE)
        await db.executescript(_CREATE_DEVICES_TABLE)
        await db.executescript(_CREATE_GLUCOSE_READINGS_TABLE)
        await db.executescript(_CREATE_READINGS_INDEX)
        await db.commit()
        logger.info("Database initialized at %s", self.config.db_path)
        return db

    async def _create_simulated_patients(self) -> None:
        """Create simulated patients and their paired devices in the database.

        Each patient gets a unique BLE address in the format
        AA:BB:CC:DD:EE:FF and an AccuChek Instant device entry.
        """
        random.seed(42)  # Reproducible simulation

        for i in range(self.config.num_patients):
            first_name = FIRST_NAMES[i % len(FIRST_NAMES)]
            last_name = LAST_NAMES[i % len(LAST_NAMES)]
            ble_address = f"SIM:{i+1:02X}:{random.randint(0,255):02X}:{random.randint(0,255):02X}"

            # Check if patient already exists
            cursor = await self._db.execute(
                "SELECT id FROM patients WHERE first_name = ? AND last_name = ?",
                (first_name, last_name),
            )
            existing = await cursor.fetchone()

            if existing is not None:
                patient_id = existing["id"]
                logger.debug("Patient %s %s already exists (id=%d)", first_name, last_name, patient_id)
            else:
                # Create patient
                dob_year = random.randint(1940, 1985)
                dob_month = random.randint(1, 12)
                dob_day = random.randint(1, 28)
                dob_str = f"{dob_year}-{dob_month:02d}-{dob_day:02d}"
                gender = random.choice(["Male", "Female"])
                family_diabetes = random.choice([True, False])
                hypertension = random.choice([True, False])

                cursor = await self._db.execute(
                    """
                    INSERT INTO patients
                        (first_name, last_name, date_of_birth, gender,
                         family_diabetes_history, hypertension_history)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (first_name, last_name, dob_str, gender, family_diabetes, hypertension),
                )
                patient_id = cursor.lastrowid
                await self._db.commit()
                logger.info(
                    "Created patient: %s %s (id=%d, diabetes_history=%s)",
                    first_name, last_name, patient_id, family_diabetes,
                )

            # Check if device already exists
            cursor = await self._db.execute(
                "SELECT id FROM devices WHERE ble_address = ?",
                (ble_address,),
            )
            existing_device = await cursor.fetchone()

            if existing_device is not None:
                device_id = existing_device["id"]
            else:
                # Create paired device
                cursor = await self._db.execute(
                    """
                    INSERT INTO devices
                        (patient_id, device_name, ble_address, is_paired, status)
                    VALUES (?, 'AccuChek Instant (Simulated)', ?, 1, 'disconnected')
                    """,
                    (patient_id, ble_address),
                )
                device_id = cursor.lastrowid
                await self._db.commit()
                logger.info(
                    "Created device for patient %d: %s (id=%d)",
                    patient_id, ble_address, device_id,
                )

            # Determine patient characteristics
            is_diabetic = random.random() < 0.4  # 40% chance of diabetic pattern
            baseline = random.uniform(
                self.config.glucose_low + 20,
                self.config.glucose_high - 20,
            )
            # Diabetic patients have higher baseline
            if is_diabetic:
                baseline = random.uniform(130.0, 200.0)

            variance = random.uniform(15.0, 40.0)

            # Find the last sequence number for this patient
            cursor = await self._db.execute(
                """
                SELECT MAX(sequence_number) as max_seq
                FROM glucose_readings
                WHERE patient_id = ?
                """,
                (patient_id,),
            )
            seq_row = await cursor.fetchone()
            last_seq = seq_row["max_seq"] if seq_row and seq_row["max_seq"] else 0

            patient = SimulatedPatient(
                patient_id=patient_id,
                first_name=first_name,
                last_name=last_name,
                ble_address=ble_address,
                device_id=device_id,
                baseline_glucose=baseline,
                glucose_variance=variance,
                is_diabetic=is_diabetic,
            )
            patient.last_sequence = last_seq or 0
            self._patients.append(patient)

        logger.info("Created %d simulated patient(s)", len(self._patients))

    async def _generate_historical_data(self) -> None:
        """Generate historical glucose readings for each patient.

        Creates readings spanning the configured number of history days,
        with the configured number of readings per day, distributed
        across realistic times (morning fasting, post-breakfast,
        afternoon, post-dinner).
        """
        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=self.config.days_history)

        total_generated = 0

        for patient in self._patients:
            # Check how many readings already exist for this patient
            cursor = await self._db.execute(
                "SELECT COUNT(*) as cnt FROM glucose_readings WHERE patient_id = ?",
                (patient.patient_id,),
            )
            count_row = await cursor.fetchone()
            existing_count = count_row["cnt"] if count_row else 0

            if existing_count > 0:
                logger.info(
                    "Patient %s %s already has %d reading(s), skipping history",
                    patient.first_name,
                    patient.last_name,
                    existing_count,
                )
                continue

            # Define realistic reading times (hours)
            reading_hours = [
                (7, "fasting"),      # Morning fasting
                (9, "postprandial"), # Post-breakfast
                (14, None),          # Afternoon
                (20, "postprandial"),  # Post-dinner
            ]

            # Generate readings for each day
            current_date = start_date
            while current_date < now:
                for hour, context in reading_hours[:self.config.readings_per_day]:
                    minute = random.randint(0, 59)
                    reading_time = current_date.replace(
                        hour=hour, minute=minute, second=0,
                        microsecond=0,
                    )
                    if reading_time > now:
                        continue

                    reading = patient.generate_glucose_reading(
                        reading_time, context
                    )

                    await self._store_reading(reading)
                    total_generated += 1

                current_date += timedelta(days=1)

        logger.info("Generated %d historical reading(s)", total_generated)

    async def _store_reading(self, reading: dict) -> int:
        """Store a single glucose reading in the database.

        Also verifies the round-trip integrity by encoding the reading
        through the GlucoseMeasurementParser encoder, then parsing it back.

        Args:
            reading: Dictionary with glucose reading data.

        Returns:
            The database row ID of the stored reading.
        """
        ts_str = reading["timestamp"].strftime("%Y-%m-%d %H:%M:%S")

        # Round-trip verification: encode then parse
        glucose_value = reading["glucose_mg_dl"]
        try:
            encoded = GlucoseMeasurementParser.encode_glucose_measurement(
                sequence_number=reading["sequence_number"],
                timestamp=reading["timestamp"],
                glucose_mg_dl=glucose_value,
                sample_type_code=1,  # Capillary whole blood
                sample_location_code=1,  # Finger
            )
            parsed_back = GlucoseMeasurementParser.parse(encoded)
            verified_mg_dl = parsed_back.get("glucose_mg_dl")

            # Log if round-trip produced a different value (due to SFLOAT precision)
            if verified_mg_dl is not None and abs(verified_mg_dl - glucose_value) > 0.5:
                logger.debug(
                    "SFLOAT round-trip: %.1f -> encoded -> parsed -> %.1f",
                    glucose_value,
                    verified_mg_dl,
                )
        except Exception as exc:
            logger.warning("Round-trip verification failed: %s", exc)

        cursor = await self._db.execute(
            """
            INSERT INTO glucose_readings
                (patient_id, glucose_mg_dl, measurement_timestamp,
                 sequence_number, source_device, context, is_synced)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (
                reading["patient_id"],
                glucose_value,
                ts_str,
                reading["sequence_number"],
                reading["source_device"],
                reading.get("context"),
            ),
        )
        await self._db.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    async def _realtime_loop(self) -> None:
        """Generate new readings at the configured interval.

        Each iteration selects a random patient and generates a new
        reading with a timestamp close to the current time, simulating
        a real glucometer sending a measurement.
        """
        logger.info(
            "Starting real-time simulation (1 reading every %ds)",
            self.config.interval_seconds,
        )

        # Contexts for random selection
        contexts = [
            None,           # Unspecified
            "fasting",      # Fasting
            "postprandial", # After meal
            "bedtime",      # Before bed
        ]

        while self._running:
            try:
                # Pick a random patient
                patient = random.choice(self._patients)

                # Generate a reading near the current time
                now = datetime.now(timezone.utc)
                jitter = random.randint(-120, 120)  # ±2 minutes
                reading_time = now + timedelta(seconds=jitter)

                # Pick a context based on time of day
                hour = now.hour
                if 5 <= hour < 9:
                    context = "fasting"
                elif 9 <= hour < 12 or 18 <= hour < 21:
                    context = "postprandial"
                elif 21 <= hour or hour < 5:
                    context = "bedtime"
                else:
                    context = random.choice(contexts)

                reading = patient.generate_glucose_reading(reading_time, context)

                # Store the reading
                reading_id = await self._store_reading(reading)

                # Simulate device lifecycle events
                await self._simulate_device_lifecycle(patient)

                logger.info(
                    "📊 New reading #%d: %s %s — %.1f mg/dL (%s) at %s",
                    reading_id,
                    patient.first_name,
                    patient.last_name,
                    reading["glucose_mg_dl"],
                    context or "unspecified",
                    reading_time.strftime("%H:%M:%S"),
                )

                # Alert if glucose is out of normal range
                glucose = reading["glucose_mg_dl"]
                if glucose < 54:
                    logger.warning(
                        "⚠️  CRITICAL LOW glucose for %s %s: %.1f mg/dL",
                        patient.first_name,
                        patient.last_name,
                        glucose,
                    )
                elif glucose < 70:
                    logger.warning(
                        "⚡ Low glucose for %s %s: %.1f mg/dL",
                        patient.first_name,
                        patient.last_name,
                        glucose,
                    )
                elif glucose > 300:
                    logger.warning(
                        "⚠️  CRITICAL HIGH glucose for %s %s: %.1f mg/dL",
                        patient.first_name,
                        patient.last_name,
                        glucose,
                    )
                elif glucose > 180:
                    logger.warning(
                        "🔺 High glucose for %s %s: %.1f mg/dL",
                        patient.first_name,
                        patient.last_name,
                        glucose,
                    )

            except Exception as exc:
                logger.error("Error generating reading: %s", exc, exc_info=True)

            if self._running:
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.config.interval_seconds,
                    )
                    break  # Shutdown requested
                except asyncio.TimeoutError:
                    pass  # Normal interval elapsed

        # Cleanup
        if self._db is not None:
            # Set all simulated devices to disconnected
            for patient in self._patients:
                try:
                    await self._db.execute(
                        "UPDATE devices SET status = 'disconnected' WHERE ble_address = ?",
                        (patient.ble_address,),
                    )
                except Exception:
                    pass
            await self._db.commit()
            await self._db.close()

        logger.info("Simulator stopped")

    async def _simulate_device_lifecycle(self, patient: SimulatedPatient) -> None:
        """Simulate device connection lifecycle events.

        Randomly transitions the device through connection states,
        mimicking a real BLE scan → connect → sync → disconnect cycle.

        Args:
            patient: The simulated patient whose device to update.
        """
        if self._db is None:
            return

        try:
            # Simulate: discovered → connecting → syncing → connected → disconnected
            states = ["disconnected", "connected", "syncing", "connected", "disconnected"]
            for state in states:
                sync_time = None
                if state == "connected":
                    sync_time = datetime.now(timezone.utc)

                if sync_time is not None:
                    sync_str = sync_time.strftime("%Y-%m-%d %H:%M:%S")
                    await self._db.execute(
                        "UPDATE devices SET status = ?, last_sync_at = ? WHERE ble_address = ?",
                        (state, sync_str, patient.ble_address),
                    )
                else:
                    await self._db.execute(
                        "UPDATE devices SET status = ? WHERE ble_address = ?",
                        (state, patient.ble_address),
                    )

            # Simulate battery drain
            cursor = await self._db.execute(
                "SELECT battery_level FROM devices WHERE ble_address = ?",
                (patient.ble_address,),
            )
            row = await cursor.fetchone()
            current_battery = row["battery_level"] if row and row["battery_level"] is not None else 100
            new_battery = max(0, current_battery - random.randint(0, 1))

            await self._db.execute(
                "UPDATE devices SET battery_level = ? WHERE ble_address = ?",
                (new_battery, patient.ble_address),
            )
            await self._db.commit()

        except Exception as exc:
            logger.warning(
                "Error simulating device lifecycle for %s: %s",
                patient.ble_address,
                exc,
            )


# ── Entry point ──────────────────────────────────────────────────────────────


async def run_simulator() -> None:
    """Create and run the BLE simulator as a standalone async application."""
    config = SimulatorConfig()
    simulator = BLESimulator(config)
    await simulator.start()


def main() -> None:
    """Entry point for running the simulator standalone.

    Usage:
        python -m ble_service.simulator
    """
    logger.info("=" * 60)
    logger.info("Diabetes MVP — BLE Simulator (No Hardware Required)")
    logger.info("=" * 60)

    try:
        asyncio.run(run_simulator())
    except KeyboardInterrupt:
        logger.info("Simulator interrupted by user")
    except Exception as exc:
        logger.critical("Simulator crashed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
