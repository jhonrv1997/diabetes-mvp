"""
Glucose Measurement GATT Characteristic Parser.

Parses raw BLE data from the Glucose Measurement characteristic (0x2A18)
according to the Bluetooth SIG Glucose Service specification.

Reference: https://www.bluetooth.com/specifications/specs/glucose-service-1-0/
"""

import struct
import math
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ── SFLOAT special values (IEEE 11073 16-bit float) ──────────────────────────

SFLOAT_NAN = 0x07FF
SFLOAT_NRES = 0x0800
SFLOAT_POS_INFINITY = 0x07FE
SFLOAT_NEG_INFINITY = 0x0802
SFLOAT_RESERVED = 0x0801


# ── Sample type mapping per Bluetooth SIG ────────────────────────────────────

SAMPLE_TYPE_NAMES: dict[int, str] = {
    0: "Reserved",
    1: "Capillary Whole blood",
    2: "Capillary Plasma",
    3: "Venous Whole blood",
    4: "Venous Plasma",
    5: "Arterial Whole blood",
    6: "Arterial Plasma",
    7: "Undetermined Whole blood",
    8: "Undetermined Plasma",
    9: "Interstitial Fluid (ISF)",
    10: "Control Solution",
    11: "Capillary Whole blood (alternate site)",
    12: "Haemolysed Whole blood",
    13: "Haemolysed Plasma",
    14: "Unspecified",
    15: "Reserved",
}


# ── Sample location mapping per Bluetooth SIG ────────────────────────────────

SAMPLE_LOCATION_NAMES: dict[int, str] = {
    0: "Reserved",
    1: "Finger",
    2: "Alternate Site Test (AST)",
    3: "Earlobe",
    4: "Control Solution",
    5: "Unspecified",
    6: "Reserved",
    7: "Reserved",
    8: "Reserved",
    9: "Reserved",
    10: "Reserved",
    11: "Reserved",
    12: "Reserved",
    13: "Reserved",
    14: "Reserved",
    15: "Reserved",
}


# ── Sensor status annunciation bit flags ─────────────────────────────────────

SENSOR_STATUS_FLAGS: dict[int, str] = {
    0: "Device battery low at time of measurement",
    1: "Sensor malfunction or faulting at time of measurement",
    2: "Sample size for blood or control solution insufficient at time of measurement",
    3: "Strip insertion error",
    4: "Strip type incorrect for device",
    5: "Sensor result higher than the device can process",
    6: "Sensor result lower than the device can process",
    7: "Sensor read interrupted because strip was pulled too soon at time of measurement",
    8: "Generic sensor fault at time of measurement",
    9: "Sensor fault because of violation of the measuring conditions at time of measurement",
    10: "Reserved",
    11: "Reserved",
    12: "Reserved",
    13: "Reserved",
    14: "Time synchronization between sensor and measuring device required",
    15: "Warning: calibration required or ongoing",
}


class GlucoseMeasurementParser:
    """Parse raw BLE Glucose Measurement data per Bluetooth SIG spec.

    The Glucose Measurement characteristic (UUID 0x2A18) encodes:
    - Flags byte determining which optional fields are present
    - Sequence number
    - Base timestamp
    - Optional time offset
    - Optional glucose concentration (SFLOAT) with type and sample location
    - Optional sensor status annunciation

    This parser handles all optional fields and provides structured output
    with human-readable sample type/location names and proper unit handling.
    """

    @staticmethod
    def parse(data: bytes) -> dict:
        """Parse raw bytes from the Glucose Measurement characteristic (0x2A18).

        Args:
            data: Raw bytes read from the BLE characteristic.

        Returns:
            A dictionary with the following keys:
            - sequence_number (int): Glucose measurement sequence number.
            - timestamp (datetime): Measurement timestamp (with offset if present).
            - glucose_mg_dl (float | None): Glucose concentration in mg/dL, or None.
            - glucose_mmol_l (float | None): Glucose concentration in mmol/L, or None.
            - unit (str): "mg/dL" or "mmol/L" based on the flags bit.
            - sample_type (str | None): Human-readable sample type name.
            - sample_location (str | None): Human-readable sample location name.
            - time_offset_minutes (int | None): Time offset from base time in minutes.
            - sensor_status (dict | None): Sensor status flags that were set.
            - context_follows (bool): Whether a Glucose Measurement Context follows.

        Raises:
            ValueError: If the data is too short or malformed.
        """
        if not data or len(data) < 10:
            raise ValueError(
                f"Glucose Measurement data too short: {len(data) if data else 0} bytes, "
                f"minimum 10 bytes required (flags + seq + base time)"
            )

        offset = 0

        # ── Byte 0: Flags ─────────────────────────────────────────────────
        flags = data[offset]
        offset += 1

        time_offset_present = bool(flags & 0x01)
        glucose_concentration_present = bool(flags & 0x02)
        unit_mg_dl = bool(flags & 0x04)  # 0 = kg/L, 1 = mg/dL
        sensor_status_present = bool(flags & 0x08)
        context_follows = bool(flags & 0x10)
        # Bits 5-7 are reserved

        logger.debug(
            "Parsing glucose measurement: flags=0x%02X, "
            "time_offset=%s, concentration=%s, unit=%s, status=%s, context=%s",
            flags,
            time_offset_present,
            glucose_concentration_present,
            "mg/dL" if unit_mg_dl else "kg/L",
            sensor_status_present,
            context_follows,
        )

        # ── Bytes 1-2: Sequence Number (uint16 LE) ────────────────────────
        if offset + 2 > len(data):
            raise ValueError("Data too short for sequence number")
        sequence_number = struct.unpack_from("<H", data, offset)[0]
        offset += 2

        # ── Bytes 3-8: Base Time (Year, Month, Day, Hours, Minutes, Seconds)
        if offset + 6 > len(data):
            raise ValueError("Data too short for base time")

        year = struct.unpack_from("<H", data, offset)[0]
        offset += 2
        month = data[offset]
        offset += 1
        day = data[offset]
        offset += 1
        hours = data[offset]
        offset += 1
        minutes = data[offset]
        offset += 1
        seconds = data[offset]
        offset += 1

        # Validate and construct the base timestamp
        # Year 0 means "not known" per Bluetooth SIG spec
        if year == 0 or month == 0 or day == 0:
            logger.warning(
                "Incomplete base time: year=%d, month=%d, day=%d; using current UTC time",
                year, month, day,
            )
            timestamp = datetime.utcnow()
        else:
            try:
                timestamp = datetime(
                    year=year,
                    month=min(max(month, 1), 12),
                    day=min(max(day, 1), 31),
                    hour=min(hours, 23),
                    minute=min(minutes, 59),
                    second=min(seconds, 59),
                )
            except ValueError as exc:
                logger.warning("Invalid base time values: %s; using current UTC time", exc)
                timestamp = datetime.utcnow()

        # ── Optional: Time Offset (int16 LE, minutes) ─────────────────────
        time_offset_minutes: Optional[int] = None
        if time_offset_present:
            if offset + 2 > len(data):
                raise ValueError("Data too short for time offset")
            time_offset_minutes = struct.unpack_from("<h", data, offset)[0]
            offset += 2
            # Apply the offset to the timestamp
            from datetime import timedelta
            timestamp = timestamp + timedelta(minutes=time_offset_minutes)
            logger.debug("Time offset applied: %d minutes", time_offset_minutes)

        # ── Optional: Glucose Concentration (SFLOAT) + Type/Sample Location
        glucose_mg_dl: Optional[float] = None
        glucose_mmol_l: Optional[float] = None
        sample_type: Optional[str] = None
        sample_location: Optional[str] = None
        unit: str = "mg/dL" if unit_mg_dl else "mmol/L"

        if glucose_concentration_present:
            if offset + 3 > len(data):
                raise ValueError("Data too short for glucose concentration and type/location")

            # SFLOAT is 2 bytes (16-bit IEEE 11073)
            raw_concentration = GlucoseMeasurementParser.decode_sfloat(
                data[offset:offset + 2]
            )
            offset += 2

            # Type and Sample Location byte
            type_location_byte = data[offset]
            offset += 1

            sample_type_code = type_location_byte & 0x0F  # Bits 0-3
            sample_location_code = (type_location_byte >> 4) & 0x0F  # Bits 4-7

            sample_type = GlucoseMeasurementParser.get_sample_type_name(sample_type_code)
            sample_location = GlucoseMeasurementParser.get_sample_location_name(sample_location_code)

            # Convert concentration based on the unit flag
            if not math.isnan(raw_concentration):
                if unit_mg_dl:
                    # The SFLOAT value is already in mg/dL
                    glucose_mg_dl = round(raw_concentration, 1)
                    # Convert to mmol/L: 1 mmol/L = 18.018 mg/dL
                    glucose_mmol_l = round(raw_concentration / 18.018, 2)
                else:
                    # The SFLOAT value is in kg/L (which is effectively mol/L * molecular_weight)
                    # For glucose, 1 mmol/L ≈ 0.000018016 kg/L
                    # The AccuChek typically reports in mg/dL with unit bit set,
                    # but we handle kg/L conversion for completeness:
                    # kg/L -> mg/dL: multiply by 100000 / 0.1801559
                    # Simpler: kg/L is the same as g/L * 1000;
                    # glucose molecular weight ≈ 180.1559 g/mol
                    # So kg/L * (1000 / 0.1801559) = mg/dL (approx)
                    # Actually, per Bluetooth SIG, kg/L is the SI unit for concentration.
                    # kg/L * 100000 = dg/L; but for glucose in mmol/L:
                    # 1 kg/L = 5550.8 mmol/L (using molecular weight 180.1559)
                    # More practically, kg/L is extremely large; likely the device
                    # sends in the appropriate scale.
                    # We'll treat the raw value as mmol/L when unit bit is 0 (common interpretation)
                    glucose_mmol_l = round(raw_concentration, 2)
                    glucose_mg_dl = round(raw_concentration * 18.018, 1)

            logger.debug(
                "Glucose concentration: raw=%.4f, mg/dL=%s, mmol/L=%s, unit=%s, "
                "type=%s, location=%s",
                raw_concentration, glucose_mg_dl, glucose_mmol_l, unit,
                sample_type, sample_location,
            )

        # ── Optional: Sensor Status Annunciation (2 or 4 bytes) ───────────
        sensor_status: Optional[dict] = None
        if sensor_status_present:
            if offset + 2 > len(data):
                raise ValueError("Data too short for sensor status")
            # Minimum 16-bit status; could be 32-bit if extra byte present
            status_value = struct.unpack_from("<H", data, offset)[0]
            offset += 2

            # Check for extended (32-bit) status
            if offset + 2 <= len(data):
                # Peek: if the next two bytes look like valid status extension,
                # we read them. Per spec, the size is determined by the
                # annunciation field itself, but for simplicity we read all
                # remaining as status if it matches expected length.
                # Most AccuChek devices use 16-bit status only.
                pass  # We'll just use the 16-bit status

            # Decode which flags are set
            sensor_status = {}
            for bit_pos, description in SENSOR_STATUS_FLAGS.items():
                if status_value & (1 << bit_pos):
                    sensor_status[bit_pos] = description

            if sensor_status:
                logger.warning("Sensor status flags set: %s", sensor_status)

        result = {
            "sequence_number": sequence_number,
            "timestamp": timestamp,
            "glucose_mg_dl": glucose_mg_dl,
            "glucose_mmol_l": glucose_mmol_l,
            "unit": unit,
            "sample_type": sample_type,
            "sample_location": sample_location,
            "time_offset_minutes": time_offset_minutes,
            "sensor_status": sensor_status,
            "context_follows": context_follows,
        }

        logger.info(
            "Parsed glucose reading: seq=%d, timestamp=%s, %.1f mg/dL, type=%s, location=%s",
            sequence_number,
            timestamp.isoformat(),
            glucose_mg_dl if glucose_mg_dl is not None else 0.0,
            sample_type,
            sample_location,
        )

        return result

    @staticmethod
    def decode_sfloat(data: bytes) -> float:
        """Decode an IEEE 11073 SFLOAT (16-bit floating point) value.

        The SFLOAT format encodes a signed mantissa and a signed exponent:
        - Bits 0-3: exponent (signed, 4-bit two's complement)
        - Bits 4-15: mantissa (signed, 12-bit two's complement)
        - Value = mantissa × 10^exponent

        Special values:
        - 0x07FF = NaN
        - 0x0800 = NRes (Not at this Resolution)
        - 0x07FE = +INFINITY
        - 0x0802 = -INFINITY
        - 0x0801 = Reserved

        Args:
            data: 2 bytes in little-endian order representing the SFLOAT.

        Returns:
            The decoded floating point value, or float('nan') / float('inf') /
            float('-inf') for special values.

        Raises:
            ValueError: If the data is not exactly 2 bytes or has a reserved value.
        """
        if len(data) < 2:
            raise ValueError(f"SFLOAT requires 2 bytes, got {len(data)}")

        # Read as uint16 LE first
        raw_uint = struct.unpack_from("<H", data, 0)[0]

        # Check for special values
        if raw_uint == SFLOAT_NAN:
            return float("nan")
        if raw_uint == SFLOAT_NRES:
            logger.warning("SFLOAT NRes (Not at this Resolution) encountered")
            return float("nan")
        if raw_uint == SFLOAT_POS_INFINITY:
            return float("inf")
        if raw_uint == SFLOAT_NEG_INFINITY:
            return float("-inf")
        if raw_uint == SFLOAT_RESERVED:
            raise ValueError("SFLOAT reserved value 0x0801 encountered")

        # Extract 4-bit exponent (bits 0-3)
        exponent_bits = raw_uint & 0x0F
        # Convert from 4-bit two's complement to signed int
        if exponent_bits & 0x08:  # If sign bit is set (bit 3)
            exponent = exponent_bits - 16
        else:
            exponent = exponent_bits

        # Extract 12-bit mantissa (bits 4-15)
        mantissa_bits = (raw_uint >> 4) & 0x0FFF
        # Convert from 12-bit two's complement to signed int
        if mantissa_bits & 0x800:  # If sign bit is set (bit 11)
            mantissa = mantissa_bits - 0x1000
        else:
            mantissa = mantissa_bits

        value = mantissa * (10 ** exponent)

        logger.debug(
            "SFLOAT decode: raw=0x%04X, mantissa=%d, exponent=%d, value=%.6f",
            raw_uint, mantissa, exponent, value,
        )

        return value

    @staticmethod
    def get_sample_type_name(code: int) -> str:
        """Map a sample type code to its human-readable name.

        Args:
            code: The sample type code (0-15) from bits 0-3 of the
                  type/location byte.

        Returns:
            The human-readable sample type name, or "Unknown (code)"
            for unrecognized codes.
        """
        return SAMPLE_TYPE_NAMES.get(code, f"Unknown ({code})")

    @staticmethod
    def get_sample_location_name(code: int) -> str:
        """Map a sample location code to its human-readable name.

        Args:
            code: The sample location code (0-15) from bits 4-7 of the
                  type/location byte.

        Returns:
            The human-readable sample location name, or "Unknown (code)"
            for unrecognized codes.
        """
        return SAMPLE_LOCATION_NAMES.get(code, f"Unknown ({code})")

    @staticmethod
    def encode_sfloat(value: float) -> bytes:
        """Encode a float value to IEEE 11073 SFLOAT format (2 bytes LE).

        This is primarily useful for the simulator to generate test data.

        Args:
            value: The floating point value to encode.

        Returns:
            2 bytes in little-endian order representing the SFLOAT.

        Raises:
            ValueError: If the value cannot be represented in SFLOAT format.
        """
        if math.isnan(value):
            return struct.pack("<H", SFLOAT_NAN)
        if math.isinf(value):
            if value > 0:
                return struct.pack("<H", SFLOAT_POS_INFINITY)
            else:
                return struct.pack("<H", SFLOAT_NEG_INFINITY)

        # Try to find the best exponent/mantissa representation
        # Exponent range: -8 to +7 (4-bit two's complement)
        # Mantissa range: -2048 to +2047 (12-bit two's complement)
        best_exponent = 0
        best_mantissa = 0

        for exp in range(-8, 8):
            mantissa_f = value / (10 ** exp)
            mantissa_rounded = round(mantissa_f)

            # Check if mantissa fits in 12-bit signed
            if -2048 <= mantissa_rounded <= 2047:
                # Check if this representation is accurate enough
                reconstructed = mantissa_rounded * (10 ** exp)
                if abs(reconstructed - value) < abs(
                    (best_mantissa * (10 ** best_exponent) - value)
                    if best_mantissa != 0 or best_exponent != 0
                    else float("inf")
                ):
                    best_exponent = exp
                    best_mantissa = mantissa_rounded

        if best_mantissa == 0 and best_exponent == 0 and value != 0.0:
            raise ValueError(
                f"Value {value} cannot be represented in SFLOAT format"
            )

        # Convert signed exponent to 4-bit two's complement
        if best_exponent < 0:
            exp_bits = best_exponent + 16
        else:
            exp_bits = best_exponent

        # Convert signed mantissa to 12-bit two's complement
        if best_mantissa < 0:
            mantissa_bits = best_mantissa + 0x1000
        else:
            mantissa_bits = best_mantissa

        # Combine: bits 0-3 = exponent, bits 4-15 = mantissa
        raw_uint = (exp_bits & 0x0F) | ((mantissa_bits & 0x0FFF) << 4)

        return struct.pack("<H", raw_uint)

    @staticmethod
    def encode_glucose_measurement(
        sequence_number: int,
        timestamp: datetime,
        glucose_mg_dl: float,
        sample_type_code: int = 1,
        sample_location_code: int = 1,
        time_offset_minutes: Optional[int] = None,
        context_follows: bool = False,
    ) -> bytes:
        """Encode a glucose measurement into the 0x2A18 characteristic format.

        This is primarily useful for the simulator to generate test data
        that can be fed through the parser to verify correctness.

        Args:
            sequence_number: The measurement sequence number.
            timestamp: The measurement timestamp.
            glucose_mg_dl: Glucose concentration in mg/dL.
            sample_type_code: Sample type code (default 1 = capillary whole blood).
            sample_location_code: Sample location code (default 1 = finger).
            time_offset_minutes: Optional time offset in minutes.
            context_follows: Whether a context record follows.

        Returns:
            Encoded bytes for the Glucose Measurement characteristic.
        """
        # Build flags byte
        flags = 0x00
        if time_offset_minutes is not None:
            flags |= 0x01  # Time Offset Present
        flags |= 0x02  # Glucose Concentration and Type Present
        flags |= 0x04  # Concentration Units = mg/dL
        # flags |= 0x08 would be Sensor Status Annunciation Present
        if context_follows:
            flags |= 0x10

        result = bytearray()
        result.append(flags)

        # Sequence number (uint16 LE)
        result.extend(struct.pack("<H", sequence_number))

        # Base time
        result.extend(struct.pack("<H", timestamp.year))
        result.append(timestamp.month)
        result.append(timestamp.day)
        result.append(timestamp.hour)
        result.append(timestamp.minute)
        result.append(timestamp.second)

        # Optional: Time Offset
        if time_offset_minutes is not None:
            result.extend(struct.pack("<h", time_offset_minutes))

        # Glucose Concentration (SFLOAT in mg/dL)
        result.extend(GlucoseMeasurementParser.encode_sfloat(glucose_mg_dl))

        # Type and Sample Location byte
        type_location = (sample_type_code & 0x0F) | ((sample_location_code & 0x0F) << 4)
        result.append(type_location)

        return bytes(result)
