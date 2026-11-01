"""Facial Liveness & Camera Frame Capture Engine for Mobile Client."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict, Any, Tuple

from src.ui.i18n import Locale, get_translation


class LivenessState(str, Enum):
    IDLE = "IDLE"
    ALIGNING = "ALIGNING"
    CHALLENGING = "CHALLENGING"
    CAPTURED = "CAPTURED"
    PASSED = "PASSED"
    FAILED = "FAILED"


class ChallengeType(str, Enum):
    BLINK = "BLINK"
    TURN_LEFT = "TURN_LEFT"
    TURN_RIGHT = "TURN_RIGHT"
    SMILE = "SMILE"


@dataclass
class BiometricFrame:
    frame_index: int
    data_bytes: bytes
    timestamp: datetime
    is_keyframe: bool = False


class LivenessCaptureSession:
    """Manages camera frame buffering, face positioning cues, and ephemeral zero-retention."""

    def __init__(self, locale: Locale = Locale.EN, challenge: ChallengeType = ChallengeType.BLINK):
        self.locale = locale
        self.challenge = challenge
        self.state: LivenessState = LivenessState.IDLE
        self.frames: List[BiometricFrame] = []
        self.captured_selfie_b64: Optional[str] = None
        self.liveness_score: float = 0.0
        self.error_message: Optional[str] = None

    def get_current_instruction(self) -> str:
        """Returns visual alignment/challenge instruction in the active locale."""
        if self.state in (LivenessState.IDLE, LivenessState.ALIGNING):
            return get_translation("liveness.instruction_center", self.locale)
        elif self.state == LivenessState.CHALLENGING:
            if self.challenge == ChallengeType.BLINK:
                return get_translation("liveness.instruction_blink", self.locale)
            elif self.challenge == ChallengeType.TURN_LEFT:
                return get_translation("liveness.instruction_turn", self.locale)
            elif self.challenge == ChallengeType.SMILE:
                return get_translation("liveness.instruction_smile", self.locale)
            return get_translation("liveness.instruction_center", self.locale)
        elif self.state == LivenessState.PASSED:
            return get_translation("liveness.success", self.locale, score=round(self.liveness_score, 2))
        elif self.state == LivenessState.FAILED:
            return self.error_message or "Liveness verification failed"
        return ""

    def start_camera(self) -> None:
        """User opens selfie frame."""
        self.state = LivenessState.ALIGNING
        self.frames.clear()

    def advance_to_challenge(self) -> None:
        """Face detected inside oval; trigger motion challenge."""
        self.state = LivenessState.CHALLENGING

    def record_frame(self, frame_bytes: bytes, is_keyframe: bool = False) -> None:
        """Buffers ephemeral frame in memory."""
        frame = BiometricFrame(
            frame_index=len(self.frames),
            data_bytes=frame_bytes,
            timestamp=datetime.now(timezone.utc),
            is_keyframe=is_keyframe,
        )
        self.frames.append(frame)

    def capture_selfie(self, raw_jpeg_bytes: Optional[bytes] = None) -> str:
        """Captures still selfie frame for anti-spoofing and face comparison."""
        payload = raw_jpeg_bytes or b"\xff\xd8\xff\xe0\x00\x10JFIF" + os.urandom(64)
        self.record_frame(payload, is_keyframe=True)
        self.captured_selfie_b64 = base64.b64encode(payload).decode("utf-8")
        self.state = LivenessState.CAPTURED
        return self.captured_selfie_b64

    def complete_liveness(self, score: float = 0.94) -> Tuple[bool, str]:
        """Processes server anti-spoofing result."""
        self.liveness_score = score
        if score >= 0.70:
            self.state = LivenessState.PASSED
            return True, get_translation("liveness.success", self.locale, score=round(score, 2))
        else:
            self.state = LivenessState.FAILED
            self.error_message = "Spoof or low liveness score detected"
            return False, self.error_message

    def purge_biometrics(self) -> None:
        """Zero-retention requirement: clear in-memory buffers immediately."""
        self.frames.clear()
        self.captured_selfie_b64 = None

    def to_api_payload(self) -> Dict[str, Any]:
        """Serializes payload for POST /v1/applications/{id}/liveness."""
        if not self.captured_selfie_b64:
            raise ValueError("No captured selfie frame available")
        return {
            "selfie_base64": self.captured_selfie_b64,
            "challenge_type": self.challenge.value,
            "frame_count": max(1, len(self.frames)),
        }
