"""
Alert Generation Service for the Diabetes Detection MVP.

Creates and manages alerts based on prediction risk levels:
  • High risk   (≥ 0.7) → immediate alert
  • Medium risk (0.4–0.7) → monitoring alert
  • Low risk    (< 0.4) → no alert
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, desc, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, Prediction, Patient
from app.schemas import AlertResponse

logger = logging.getLogger(__name__)


class AlertService:
    """Service for creating and managing risk-based alerts."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Alert creation ──────────────────────────────────────────────────────

    async def check_and_create_alerts(
        self,
        prediction: Prediction,
    ) -> Optional[AlertResponse]:
        """
        Check prediction result and create an alert if the risk level warrants it.

        Parameters
        ----------
        prediction : Prediction
            A newly created Prediction database row.

        Returns
        -------
        AlertResponse | None
            The created alert, or None if no alert was needed.
        """
        risk_level = prediction.risk_level
        probability = prediction.risk_probability

        # Determine alert type and severity
        if risk_level == "high":
            alert_type = "immediate"
            severity = "high"
        elif risk_level == "medium":
            alert_type = "monitoring"
            severity = "medium"
        else:
            # Low risk — no alert
            return None

        # Build alert message
        message = self._build_alert_message(
            patient_id=prediction.patient_id,
            risk_level=risk_level,
            probability=probability,
        )

        # Check if there is already an active alert for this patient with
        # the same severity — avoid duplicate alerts
        existing = await self.db.execute(
            select(Alert).where(
                and_(
                    Alert.patient_id == prediction.patient_id,
                    Alert.severity == severity,
                    Alert.is_active == True,  # noqa: E712
                )
            )
        )
        if existing.scalar_one_or_none() is not None:
            logger.info(
                "Active %s alert already exists for patient %d — skipping.",
                severity,
                prediction.patient_id,
            )
            return None

        # Create the alert
        alert = Alert(
            prediction_id=prediction.id,
            patient_id=prediction.patient_id,
            alert_type=alert_type,
            severity=severity,
            risk_probability=probability,
            message=message,
            is_active=True,
        )
        self.db.add(alert)
        await self.db.flush()
        await self.db.refresh(alert)

        # Get patient name for response
        patient_name = await self._get_patient_name(prediction.patient_id)

        logger.info(
            "Created %s alert for patient %d (risk=%.2f%%)",
            alert_type,
            prediction.patient_id,
            probability * 100,
        )

        return AlertResponse(
            id=alert.id,
            prediction_id=alert.prediction_id,
            patient_id=alert.patient_id,
            patient_name=patient_name,
            alert_type=alert.alert_type,
            severity=alert.severity,
            risk_probability=alert.risk_probability,
            message=alert.message,
            is_active=alert.is_active,
            dismissed_by=alert.dismissed_by,
            dismissed_at=alert.dismissed_at,
            created_at=alert.created_at,
        )

    # ── Query methods ───────────────────────────────────────────────────────

    async def get_active_alerts(self) -> list[AlertResponse]:
        """
        Get all active (non-dismissed) alerts, ordered by creation date
        (most recent first).

        Returns
        -------
        list[AlertResponse]
        """
        result = await self.db.execute(
            select(Alert)
            .where(Alert.is_active == True)  # noqa: E712
            .order_by(desc(Alert.created_at))
            .limit(200)
        )
        alerts = result.scalars().all()

        response_list = []
        for alert in alerts:
            patient_name = await self._get_patient_name(alert.patient_id)
            response_list.append(
                AlertResponse(
                    id=alert.id,
                    prediction_id=alert.prediction_id,
                    patient_id=alert.patient_id,
                    patient_name=patient_name,
                    alert_type=alert.alert_type,
                    severity=alert.severity,
                    risk_probability=alert.risk_probability,
                    message=alert.message,
                    is_active=alert.is_active,
                    dismissed_by=alert.dismissed_by,
                    dismissed_at=alert.dismissed_at,
                    created_at=alert.created_at,
                )
            )
        return response_list

    async def get_patient_alerts(self, patient_id: int) -> list[AlertResponse]:
        """
        Get all alerts (both active and dismissed) for a specific patient.

        Parameters
        ----------
        patient_id : int

        Returns
        -------
        list[AlertResponse]
        """
        result = await self.db.execute(
            select(Alert)
            .where(Alert.patient_id == patient_id)
            .order_by(desc(Alert.created_at))
            .limit(100)
        )
        alerts = result.scalars().all()

        patient_name = await self._get_patient_name(patient_id)

        return [
            AlertResponse(
                id=alert.id,
                prediction_id=alert.prediction_id,
                patient_id=alert.patient_id,
                patient_name=patient_name,
                alert_type=alert.alert_type,
                severity=alert.severity,
                risk_probability=alert.risk_probability,
                message=alert.message,
                is_active=alert.is_active,
                dismissed_by=alert.dismissed_by,
                dismissed_at=alert.dismissed_at,
                created_at=alert.created_at,
            )
            for alert in alerts
        ]

    # ── Dismiss alert ───────────────────────────────────────────────────────

    async def dismiss_alert(
        self,
        alert_id: int,
        dismissed_by: Optional[int] = None,
    ) -> Optional[AlertResponse]:
        """
        Dismiss an active alert.

        Parameters
        ----------
        alert_id : int
            ID of the alert to dismiss.
        dismissed_by : int | None
            User ID who dismissed the alert.

        Returns
        -------
        AlertResponse | None
            The dismissed alert, or None if not found / already dismissed.
        """
        result = await self.db.execute(
            select(Alert).where(Alert.id == alert_id)
        )
        alert = result.scalar_one_or_none()

        if alert is None:
            return None

        if not alert.is_active:
            return None

        alert.is_active = False
        alert.dismissed_by = dismissed_by
        alert.dismissed_at = datetime.utcnow()

        await self.db.flush()
        await self.db.refresh(alert)

        patient_name = await self._get_patient_name(alert.patient_id)

        logger.info(
            "Alert %d dismissed for patient %d", alert_id, alert.patient_id
        )

        return AlertResponse(
            id=alert.id,
            prediction_id=alert.prediction_id,
            patient_id=alert.patient_id,
            patient_name=patient_name,
            alert_type=alert.alert_type,
            severity=alert.severity,
            risk_probability=alert.risk_probability,
            message=alert.message,
            is_active=alert.is_active,
            dismissed_by=alert.dismissed_by,
            dismissed_at=alert.dismissed_at,
            created_at=alert.created_at,
        )

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _build_alert_message(
        self,
        patient_id: int,
        risk_level: str,
        probability: float,
    ) -> str:
        """Build a human-readable alert message."""
        if risk_level == "high":
            return (
                f"⚠️ HIGH RISK ALERT: Patient #{patient_id} has a "
                f"{probability:.0%} probability of Type 2 Diabetes. "
                f"Immediate clinical review recommended."
            )
        elif risk_level == "medium":
            return (
                f"⚡ MEDIUM RISK: Patient #{patient_id} has a "
                f"{probability:.0%} probability of Type 2 Diabetes. "
                f"Schedule follow-up assessment."
            )
        return (
            f"Patient #{patient_id} — risk level: {risk_level} "
            f"({probability:.0%})"
        )

    async def _get_patient_name(self, patient_id: int) -> str:
        """Look up patient name from the database."""
        result = await self.db.execute(
            select(Patient).where(Patient.id == patient_id)
        )
        patient = result.scalar_one_or_none()
        if patient:
            return f"{patient.first_name} {patient.last_name}"
        return f"Patient #{patient_id}"
