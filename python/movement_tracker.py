"""
Movement Tracker - MediaPipe Pose to OSC + Body Segmentation Mask
Tracks multiple people's body movements and sends to TouchDesigner.
Outputs body segmentation mask via shared memory (mmap) for real-time
consumption by TouchDesigner's Script TOP.
"""

import cv2
import mediapipe as mp
from pythonosc import udp_client
import numpy as np
import mmap
import os
import time
import json
import logging
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)

# --- Shared memory mask config ---
MASK_PATH = "/tmp/djsam_bodymask.raw"
MASK_W, MASK_H = 640, 480  # Resolution of the segmentation mask
# NOTE: Header size MUST match body_mask_sender.py (the external writer).
# body_mask_sender.py uses a 4-byte uint32 frame counter only.
# A previous mismatch here (8 bytes) caused an _platform_memmove
# EXC_BAD_ACCESS segfault inside TouchDesigner during project onStart
# because the consumer tried to mmap 4 bytes past the file end.
HEADER_SIZE = 4  # 4 bytes frame counter (uint32)
TOTAL_SIZE = HEADER_SIZE + MASK_W * MASK_H

# --- Visual mode (flame / lightning) ---
# Maps the human-readable mode name to the integer index TD's Switch TOP uses.
# Broadcast on OSC so TouchDesigner can swap the body-outline shader live.
# See configs/visual_mode.json and docs/setup/visual_mode_toggle.md.
VISUAL_MODE_CONFIG = "configs/visual_mode.json"
MODE_INDEX = {"flame": 0, "lightning": 1}
DEFAULT_VISUAL_MODE = "flame"


class MovementTracker:
    def __init__(
        self,
        osc_ip: str = "127.0.0.1",
        osc_port: int = 7000,
        config_path: str = "configs/movement_mappings.json",
        max_people: int = 4,
        camera_id: int = 0,
        enable_segmentation: bool = True,
        mask_path: str = MASK_PATH,
        visual_mode_config_path: str = VISUAL_MODE_CONFIG,
    ):
        """
        Initialize movement tracker with multi-person support + body segmentation.

        Args:
            osc_ip: IP address for OSC messages (TouchDesigner)
            osc_port: Port for OSC messages
            config_path: Path to movement mappings config
            max_people: Maximum number of people to track (1-4)
            camera_id: Camera device index
            enable_segmentation: Enable body segmentation mask output
            mask_path: Path to mmap file for segmentation mask
        """
        # MediaPipe setup
        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils
        self.mp_holistic = mp.solutions.holistic

        # Segmentation config
        self.enable_segmentation = enable_segmentation
        self.mask_path = mask_path
        self.mask_mmap = None
        self.mask_fh = None
        self.frame_counter = 0
        # Latest contour pixel count (set by _process_segmentation). Lets callers
        # / tests read how thin the emitted outline is. 0 until first frame.
        self.last_contour_px = 0

        # Visual mode (flame/lightning). Re-read from disk each broadcast so a
        # JSON edit switches the TD shader live without restarting the tracker.
        self.visual_mode_config_path = visual_mode_config_path
        self.visual_mode = DEFAULT_VISUAL_MODE
        self.visual_mode_index = MODE_INDEX[DEFAULT_VISUAL_MODE]
        self._loop_i = 0  # per-iteration counter for throttled broadcasts
        self._load_visual_mode()

        # Create separate pose detectors for each person
        self.max_people = min(max_people, 4)  # Limit to 4 for performance
        self.pose_detectors = []
        for i in range(self.max_people):
            detector = self.mp_pose.Pose(
                static_image_mode=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
                model_complexity=1,
                enable_segmentation=self.enable_segmentation,
                smooth_segmentation=self.enable_segmentation,
                smooth_landmarks=True,
            )
            self.pose_detectors.append(detector)

        # OSC client to send to TouchDesigner
        self.osc_client = udp_client.SimpleUDPClient(osc_ip, osc_port)

        # Webcam
        self.cap = cv2.VideoCapture(camera_id)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        # Movement tracking state for each person
        self.prev_positions: List[Dict[str, float]] = [
            {} for _ in range(self.max_people)
        ]
        self.motion_energy: List[float] = [0.0 for _ in range(self.max_people)]
        self.tracking_active: List[bool] = [False for _ in range(self.max_people)]
        self.person_boxes: List[Optional[tuple]] = [
            None for _ in range(self.max_people)
        ]

        # Load configuration
        self.config = self._load_config(config_path)

        # Performance monitoring
        self.frame_times = []
        self.fps = 0

        # Initialize segmentation shared memory
        if self.enable_segmentation:
            self._init_mask_mmap()

    # ------------------------------------------------------------------
    # Segmentation mask shared memory
    # ------------------------------------------------------------------
    def _init_mask_mmap(self):
        """Create / open the mmap file for body segmentation mask output."""
        if not os.path.exists(self.mask_path):
            with open(self.mask_path, "wb") as f:
                f.write(bytes(TOTAL_SIZE))
            logger.info(f"Created mask mmap file: {self.mask_path}")
        self.mask_fh = open(self.mask_path, "r+b")
        self.mask_mmap = mmap.mmap(self.mask_fh.fileno(), TOTAL_SIZE)
        logger.info(
            f"Segmentation mask mmap ready: {self.mask_path}  ({MASK_W}x{MASK_H})"
        )

    def _write_mask(self, mask_array: np.ndarray):
        """Write a grayscale mask frame into shared memory.
        Header layout (8 bytes):
            [0:4]  uint32 frame counter
            [4:8]  uint32 timestamp in milliseconds (wraps every ~49 days)
        Body:
            [8:]   MASK_W * MASK_H bytes, row-major, uint8 0-255
        """
        if self.mask_mmap is None:
            return
        # Header is a single uint32 frame counter (4 bytes) to match
        # body_mask_sender.py. Timestamp is no longer embedded — if you
        # need it, add a separate OSC channel rather than re-widening
        # the header (that mismatch caused a segfault in TD).
        header = np.uint32(self.frame_counter).tobytes()
        self.mask_mmap.seek(0)
        self.mask_mmap.write(header)
        self.mask_mmap.write(mask_array.tobytes())
        self.mask_mmap.flush()

    def _process_segmentation(self, results_list) -> np.ndarray:
        """Merge segmentation masks from all detected people into one grayscale mask,
        then extract a thin body CONTOUR (silhouette edge) — not a filled blob.

        Returns MASK_H x MASK_W uint8 array carrying a ~1-2 px outline.

        EDGE-CONFINED OUTLINE FIX (2026-06-05) ---------------------------------
        Previously this emitted a SOLID FILLED silhouette, then dilate(2x) +
        GaussianBlur(15x15), i.e. a blob expanded ~10 px and feathered into a
        ~15 px ramp. That filled, fattened, feathered mask is the root cause of
        the "aura covering the body" problem: every downstream stage (Edge TOP,
        edge_blur, shader expansion, size-12 bloom) only widened it further, so
        the output read as a glowing haze around the body, never an outline.

        Per docs/audits/baseline_outline_audit_2026-06-05.md (Cause A, Section 5
        Option 1), we now extract a crisp contour at the source with a
        morphological gradient (dilate - erode), so body_mask_top carries an
        OUTLINE instead of a blob. Stylization downstream is then confined to a
        thin band. The old dilate + GaussianBlur fill-expansion is removed; the
        resize uses NEAREST (not LINEAR) so the thin line is not re-feathered
        back into a ramp during scaling.
        -----------------------------------------------------------------------
        """
        combined = None
        for results in results_list:
            if results is not None and results.segmentation_mask is not None:
                raw = results.segmentation_mask  # float32 [0,1]
                if combined is None:
                    combined = raw.copy()
                else:
                    # Union of masks (max)
                    if combined.shape == raw.shape:
                        combined = np.maximum(combined, raw)
                    else:
                        raw_resized = cv2.resize(
                            raw, (combined.shape[1], combined.shape[0])
                        )
                        combined = np.maximum(combined, raw_resized)

        if combined is None:
            return np.zeros((MASK_H, MASK_W), dtype=np.uint8)

        # Threshold to a crisp binary silhouette (no feathering).
        binary = (combined > 0.5).astype(np.uint8) * 255

        # Extract a thin, constant-width contour. MORPH_GRADIENT = dilate - erode,
        # which leaves only the silhouette boundary. A 3x3 kernel yields a ~1-2 px
        # line — the "edge-confined" primitive the audit identified as missing.
        kernel = np.ones((3, 3), np.uint8)
        outline = cv2.morphologyEx(binary, cv2.MORPH_GRADIENT, kernel)
        # To deliberately thicken into a "neon tube" look, uncomment (adds ~1 px
        # per iteration). Left off by default for the thinnest baseline outline:
        # outline = cv2.dilate(outline, kernel, iterations=1)

        # Instrumentation: contour pixel count. A thin outline is a SMALL fraction
        # of the frame; a filled blob would be tens of thousands of px. Throttled
        # to ~1 log/sec so Thomas can confirm "this many px = line, not blob" live.
        self.last_contour_px = int(np.count_nonzero(outline))
        if self.frame_counter % 30 == 0:
            total_px = outline.shape[0] * outline.shape[1]
            pct = (self.last_contour_px / total_px * 100.0) if total_px else 0.0
            logger.info(
                "contour px=%d (%.2f%% of %dx%d) — thin outline if low, blob if high",
                self.last_contour_px,
                pct,
                outline.shape[1],
                outline.shape[0],
            )

        # Resize to output dimensions. NEAREST preserves the thin line (LINEAR
        # would smear it back into a soft ramp — the very thing we removed).
        return cv2.resize(outline, (MASK_W, MASK_H), interpolation=cv2.INTER_NEAREST)

    def _load_config(self, path: str) -> dict:
        """Load movement mappings configuration"""
        try:
            with open(path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: Config file {path} not found, using defaults")
            return {}

    # ------------------------------------------------------------------
    # Visual mode (flame / lightning) toggle
    # ------------------------------------------------------------------
    def _load_visual_mode(self):
        """Read the active visual mode from configs/visual_mode.json.

        Called on init and again before each OSC broadcast, so editing the JSON
        switches the TouchDesigner shader live (no tracker restart). On a missing
        or malformed file we keep the last good mode and carry on — the outline
        itself must never go down because a toggle file is briefly unreadable.
        """
        try:
            with open(self.visual_mode_config_path, "r") as f:
                cfg = json.load(f)
            mode = str(cfg.get("mode", DEFAULT_VISUAL_MODE)).strip().lower()
            if mode in MODE_INDEX:
                self.visual_mode = mode
                self.visual_mode_index = MODE_INDEX[mode]
            else:
                logger.warning(
                    "visual_mode '%s' not in %s — keeping '%s'",
                    mode,
                    list(MODE_INDEX),
                    self.visual_mode,
                )
        except FileNotFoundError:
            pass  # no config yet -> default mode, no noise
        except (json.JSONDecodeError, ValueError, OSError) as e:
            logger.warning(
                "visual_mode config unreadable (%s) — keeping '%s'", e, self.visual_mode
            )

    def _send_visual_mode(self):
        """Broadcast the current visual mode on OSC for TouchDesigner.

        Sends the integer index (drives a Switch TOP) and the name string (for
        DAT-based readers). Re-reads the config first so live edits propagate.
        """
        self._load_visual_mode()
        try:
            self.osc_client.send_message("/visual/mode", float(self.visual_mode_index))
            self.osc_client.send_message("/visual/mode_name", self.visual_mode)
        except Exception as e:
            logger.debug("visual mode OSC send error: %s", e)

    def detect_people_regions(self, frame):
        """
        Detect multiple people in frame and return bounding regions
        Uses simple person detection based on pose landmarks
        """
        # For initial implementation, we'll divide the frame into regions
        # and process each region separately
        height, width = frame.shape[:2]

        regions = []
        if self.max_people == 1:
            regions = [(0, 0, width, height)]
        elif self.max_people == 2:
            # Split frame vertically
            mid = width // 2
            regions = [(0, 0, mid + 100, height), (mid - 100, 0, width, height)]
        elif self.max_people == 3:
            third = width // 3
            regions = [
                (0, 0, third + 50, height),
                (third - 50, 0, 2 * third + 50, height),
                (2 * third - 50, 0, width, height),
            ]
        elif self.max_people >= 4:
            # 2x2 grid
            mid_w = width // 2
            mid_h = height // 2
            regions = [
                (0, 0, mid_w + 100, mid_h + 100),
                (mid_w - 100, 0, width, mid_h + 100),
                (0, mid_h - 100, mid_w + 100, height),
                (mid_w - 100, mid_h - 100, width, height),
            ]

        return regions

    def calculate_metrics(self, landmarks, person_id: int = 0) -> Dict[str, float]:
        """
        Extract meaningful movement metrics from pose landmarks

        Args:
            landmarks: MediaPipe pose landmarks
            person_id: ID of the person being tracked

        Returns:
            Dictionary of movement metrics
        """
        # Key landmarks (MediaPipe indices)
        left_wrist = landmarks[15]
        right_wrist = landmarks[16]
        left_shoulder = landmarks[11]
        right_shoulder = landmarks[12]
        nose = landmarks[0]
        left_hip = landmarks[23]
        right_hip = landmarks[24]

        metrics = {
            # Hand positions (normalized 0-1, origin top-left)
            "left_hand_x": left_wrist.x,
            "left_hand_y": left_wrist.y,
            "right_hand_x": right_wrist.x,
            "right_hand_y": right_wrist.y,
            # Hand height (relative to shoulders, negative = above)
            "left_hand_height": left_shoulder.y - left_wrist.y,
            "right_hand_height": right_shoulder.y - right_wrist.y,
            # Hand spread (horizontal distance)
            "hand_spread": abs(right_wrist.x - left_wrist.x),
            # Body center vertical (0=top, 1=bottom)
            "body_height": (left_hip.y + right_hip.y) / 2,
            # Head position
            "head_x": nose.x,
            "head_y": nose.y,
            # Shoulder tilt (positive = right side lower)
            "shoulder_tilt": left_shoulder.y - right_shoulder.y,
        }

        # Calculate motion energy (velocity-based)
        if self.prev_positions[person_id]:
            motion = 0.0
            tracked_points = [
                "left_hand_x",
                "left_hand_y",
                "right_hand_x",
                "right_hand_y",
            ]

            for key in tracked_points:
                if key in self.prev_positions[person_id]:
                    delta = abs(metrics[key] - self.prev_positions[person_id][key])
                    motion += delta

            # Scale and smooth
            self.motion_energy[person_id] = motion * 100  # Scale up for visibility

        metrics["motion_energy"] = self.motion_energy[person_id]

        # Store for next frame
        self.prev_positions[person_id] = metrics.copy()

        return metrics

    def send_osc_messages(self, metrics: Dict[str, float], person_id: int = 0):
        """Send all metrics via OSC to TouchDesigner for a specific person"""
        try:
            for key, value in metrics.items():
                # Use person_id in OSC address: /movement/person1/left_hand_x
                address = f"/movement/person{person_id + 1}/{key}"
                self.osc_client.send_message(address, float(value))

            # Send tracking status for this person
            self.osc_client.send_message(
                f"/movement/person{person_id + 1}/tracking_active", 1.0
            )

        except Exception as e:
            print(f"OSC send error for person {person_id}: {e}")

    def send_tracking_lost(self, person_id: int = 0):
        """Send tracking lost signal for a specific person"""
        try:
            self.osc_client.send_message(
                f"/movement/person{person_id + 1}/tracking_active", 0.0
            )
        except Exception as e:
            print(f"OSC send error: {e}")

    def send_global_stats(self, num_people: int):
        """Send overall tracking statistics"""
        try:
            self.osc_client.send_message("/movement/num_people", float(num_people))

            # Send average motion energy across all people
            active_energies = [
                e for i, e in enumerate(self.motion_energy) if self.tracking_active[i]
            ]
            if active_energies:
                avg_energy = sum(active_energies) / len(active_energies)
                self.osc_client.send_message("/movement/avg_energy", float(avg_energy))
        except Exception as e:
            print(f"OSC send error: {e}")

    def calculate_fps(self, frame_time: float):
        """Calculate rolling average FPS"""
        self.frame_times.append(frame_time)
        if len(self.frame_times) > 30:
            self.frame_times.pop(0)

        if self.frame_times:
            avg_time = sum(self.frame_times) / len(self.frame_times)
            self.fps = 1.0 / avg_time if avg_time > 0 else 0

    def draw_overlay(
        self, frame, landmarks, metrics: Dict[str, float], person_id: int = 0
    ):
        """Draw tracking visualization on frame for a specific person"""
        # Color per person
        colors = [
            (0, 255, 0),  # Green - Person 1
            (255, 0, 0),  # Blue - Person 2
            (0, 255, 255),  # Yellow - Person 3
            (255, 0, 255),  # Magenta - Person 4
        ]
        color = colors[person_id % len(colors)]

        # Draw pose landmarks
        self.mp_drawing.draw_landmarks(
            frame,
            landmarks,
            self.mp_pose.POSE_CONNECTIONS,
            self.mp_drawing.DrawingSpec(color=color, thickness=2),
            self.mp_drawing.DrawingSpec(color=color, thickness=2),
        )

        # Draw person ID label near head
        if landmarks:
            nose = landmarks.landmark[0]
            h, w, _ = frame.shape
            text_x = int(nose.x * w)
            text_y = int(nose.y * h) - 20
            cv2.putText(
                frame,
                f"P{person_id + 1}",
                (text_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                color,
                3,
            )

        return frame

    def run(self, show_preview: bool = True):
        """
        Main tracking loop with multi-person support + segmentation mask output.

        Args:
            show_preview: Whether to display visualization window
        """
        seg_status = "ON" if self.enable_segmentation else "OFF"
        print("Movement Tracker started (Multi-Person Mode)...")
        print(f"Tracking up to {self.max_people} people")
        print(f"Segmentation mask: {seg_status}")
        if self.enable_segmentation:
            print(f"  Mask file : {self.mask_path}")
            print(f"  Mask size : {MASK_W}x{MASK_H} ({TOTAL_SIZE} bytes)")
        print(f"Sending OSC to {self.osc_client._address}:{self.osc_client._port}")
        print("Press ESC to quit")

        try:
            while self.cap.isOpened():
                frame_start = time.time()

                success, frame = self.cap.read()
                if not success:
                    print("Failed to read frame")
                    continue

                # Flip frame horizontally for mirror view
                frame = cv2.flip(frame, 1)

                # Convert to RGB for MediaPipe
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Get regions for multi-person detection
                regions = self.detect_people_regions(frame)

                # Collect results for segmentation merge
                all_results = []

                # Track people in each region
                num_people_tracked = 0
                for person_id in range(min(self.max_people, len(regions))):
                    x1, y1, x2, y2 = regions[person_id]

                    # Ensure bounds are valid
                    x1, y1 = max(0, x1), max(0, y1)
                    x2 = min(frame.shape[1], x2)
                    y2 = min(frame.shape[0], y2)

                    # Extract region
                    region = frame_rgb[y1:y2, x1:x2]

                    if region.size == 0:
                        all_results.append(None)
                        continue

                    # Process region with person-specific detector
                    results = self.pose_detectors[person_id].process(region)
                    all_results.append(results)

                    if results.pose_landmarks:
                        # Extract and send metrics for this person
                        landmarks = results.pose_landmarks.landmark

                        # Adjust landmark coordinates to full frame
                        region_width = x2 - x1
                        region_height = y2 - y1
                        for landmark in landmarks:
                            landmark.x = (landmark.x * region_width + x1) / frame.shape[
                                1
                            ]
                            landmark.y = (
                                landmark.y * region_height + y1
                            ) / frame.shape[0]

                        metrics = self.calculate_metrics(landmarks, person_id)
                        self.send_osc_messages(metrics, person_id)

                        self.tracking_active[person_id] = True
                        num_people_tracked += 1

                        # Draw visualization
                        if show_preview:
                            frame = self.draw_overlay(
                                frame, results.pose_landmarks, metrics, person_id
                            )
                    else:
                        # Tracking lost for this person
                        if self.tracking_active[person_id]:
                            self.send_tracking_lost(person_id)
                            self.tracking_active[person_id] = False

                # ------ Segmentation mask output ------
                if self.enable_segmentation:
                    mask = self._process_segmentation(all_results)
                    self._write_mask(mask)
                    self.frame_counter += 1

                    # Send mask-active flag via OSC so TD knows mask is streaming
                    try:
                        self.osc_client.send_message("/movement/mask_active", 1.0)
                    except Exception:
                        pass

                # Send global statistics
                self.send_global_stats(num_people_tracked)

                # Broadcast visual mode (flame/lightning) ~1x/sec so TD can swap
                # the body-outline shader live by reading /visual/mode.
                if self._loop_i % 30 == 0:
                    self._send_visual_mode()
                self._loop_i += 1

                # Calculate FPS
                frame_time = time.time() - frame_start
                self.calculate_fps(frame_time)

                # Draw global info overlay
                if show_preview:
                    y_offset = 30
                    info_lines = [
                        f"FPS: {self.fps:.1f}",
                        f"People Tracked: {num_people_tracked}/{self.max_people}",
                        f"Segmentation: {seg_status}",
                        "Mode: Multi-Person",
                    ]

                    for i, line in enumerate(info_lines):
                        cv2.putText(
                            frame,
                            line,
                            (10, y_offset + i * 30),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.7,
                            (255, 255, 255),
                            2,
                        )

                    # Show mask preview in corner
                    if self.enable_segmentation and mask is not None:
                        mask_preview = cv2.resize(mask, (160, 120))
                        mask_bgr = cv2.cvtColor(mask_preview, cv2.COLOR_GRAY2BGR)
                        frame[10:130, frame.shape[1] - 170 : frame.shape[1] - 10] = (
                            mask_bgr
                        )

                    cv2.imshow("Movement Tracking (Multi-Person)", frame)
                    if cv2.waitKey(5) & 0xFF == 27:  # ESC key
                        break

        except KeyboardInterrupt:
            print("\nStopping tracker...")
        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        self.cap.release()
        cv2.destroyAllWindows()
        for detector in self.pose_detectors:
            detector.close()
        # Close mmap
        if self.mask_mmap is not None:
            self.mask_mmap.close()
        if self.mask_fh is not None:
            self.mask_fh.close()
        print("Movement tracker stopped")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Touchdesigner DJ Suite Movement Tracker + Body Segmentation"
    )
    parser.add_argument(
        "--max-people", type=int, default=2, help="Max people to track (1-4)"
    )
    parser.add_argument("--camera", type=int, default=0, help="Camera device index")
    parser.add_argument(
        "--no-preview", action="store_true", help="Disable preview window"
    )
    parser.add_argument(
        "--no-segmentation", action="store_true", help="Disable body segmentation mask"
    )
    parser.add_argument("--osc-ip", default="127.0.0.1", help="OSC target IP")
    parser.add_argument("--osc-port", type=int, default=7000, help="OSC target port")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    tracker = MovementTracker(
        max_people=args.max_people,
        camera_id=args.camera,
        enable_segmentation=not args.no_segmentation,
        osc_ip=args.osc_ip,
        osc_port=args.osc_port,
    )
    tracker.run(show_preview=not args.no_preview)
