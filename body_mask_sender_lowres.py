#!/usr/bin/env python3
import argparse, cv2, numpy as np, mmap, os, sys, time, logging

try:
    from pythonosc import udp_client
    OSC_AVAILABLE = True
except ImportError:
    OSC_AVAILABLE = False

try:
    import mediapipe as mp
except ImportError:
    print("ERROR: mediapipe not installed. Run: pip3.11 install mediapipe")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

MASK_PATH = "/tmp/djsam_bodymask.raw"
MASK_W, MASK_H = 320, 240
HEADER_SIZE = 4
TOTAL_SIZE = HEADER_SIZE + MASK_W * MASK_H

def init_mask_file():
    if not os.path.exists(MASK_PATH):
        with open(MASK_PATH, 'wb') as f:
            f.write(bytes(TOTAL_SIZE))
        logger.info(f'Created mask file: {MASK_PATH}')
    fh = open(MASK_PATH, 'r+b')
    mm = mmap.mmap(fh.fileno(), TOTAL_SIZE)
    return fh, mm

def write_mask(mm, frame_num, mask_array):
    header = np.uint32(frame_num).tobytes()
    mm.seek(0)
    mm.write(header)
    mm.write(mask_array.tobytes())
    mm.flush()

def run(camera_id=0, show_preview=True, send_osc=True, osc_port=7000):
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(
        static_image_mode=False, model_complexity=1,
        smooth_landmarks=True, enable_segmentation=True,
        smooth_segmentation=True,
        min_detection_confidence=0.5, min_tracking_confidence=0.5,
    )
    cap = cv2.VideoCapture(camera_id)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)
    if not cap.isOpened():
        logger.error(f'Cannot open camera {camera_id}')
        sys.exit(1)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    logger.info(f'Camera opened: {actual_w}x{actual_h}')

    fh, mm = init_mask_file()
    logger.info(f'Mask mmap ready: {MASK_PATH}')

    osc_client = None
    if send_osc and OSC_AVAILABLE:
        osc_client = udp_client.SimpleUDPClient('127.0.0.1', osc_port)
        logger.info(f'OSC -> 127.0.0.1:{osc_port}')

    frame_num = 0
    fps_smooth = 30.0

    try:
        while True:
            t0 = time.time()
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(rgb)

            if results.segmentation_mask is not None:
                raw_mask = results.segmentation_mask
                binary_mask = (raw_mask > 0.5).astype(np.uint8) * 255
                kernel = np.ones((5, 5), np.uint8)
                binary_mask = cv2.dilate(binary_mask, kernel, iterations=2)
                binary_mask = cv2.GaussianBlur(binary_mask, (15, 15), 0)
                mask_out = cv2.resize(binary_mask, (MASK_W, MASK_H), interpolation=cv2.INTER_LINEAR)
            else:
                mask_out = np.zeros((MASK_H, MASK_W), dtype=np.uint8)

            write_mask(mm, frame_num, mask_out)

            if osc_client and results.pose_landmarks:
                lm = results.pose_landmarks.landmark
                osc_client.send_message('/movement/person1/hand/left/x', lm[mp_pose.PoseLandmark.LEFT_WRIST].x)
                osc_client.send_message('/movement/person1/hand/left/y', lm[mp_pose.PoseLandmark.LEFT_WRIST].y)
                osc_client.send_message('/movement/person1/hand/right/x', lm[mp_pose.PoseLandmark.RIGHT_WRIST].x)
                osc_client.send_message('/movement/person1/hand/right/y', lm[mp_pose.PoseLandmark.RIGHT_WRIST].y)
                osc_client.send_message('/movement/person1/hand/left/height', 1.0 - lm[mp_pose.PoseLandmark.LEFT_WRIST].y)
                osc_client.send_message('/movement/person1/hand/right/height', 1.0 - lm[mp_pose.PoseLandmark.RIGHT_WRIST].y)
                osc_client.send_message('/movement/person1/motion/energy',
                    abs(lm[mp_pose.PoseLandmark.LEFT_WRIST].x - lm[mp_pose.PoseLandmark.RIGHT_WRIST].x))

            if show_preview:
                display = frame.copy()
                if results.segmentation_mask is not None:
                    mask_vis = (results.segmentation_mask * 255).astype(np.uint8)
                    mask_colored = cv2.applyColorMap(mask_vis, cv2.COLORMAP_INFERNO)
                    display = cv2.addWeighted(display, 0.6, mask_colored, 0.4, 0)
                if results.pose_landmarks:
                    mp.solutions.drawing_utils.draw_landmarks(display, results.pose_landmarks, mp_pose.POSE_CONNECTIONS)
                dt = time.time() - t0
                fps_smooth = 0.9 * fps_smooth + 0.1 * (1.0 / max(dt, 0.001))
                cv2.putText(display, f'FPS: {fps_smooth:.0f} Mask: {"YES" if results.segmentation_mask is not None else "NO"}',
                            (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.imshow('DJ Sam Body Segmentation', display)
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break

            frame_num += 1
    except KeyboardInterrupt:
        logger.info('Stopped')
    finally:
        cap.release()
        mm.close()
        fh.close()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--camera', type=int, default=0)
    parser.add_argument('--no-preview', action='store_true')
    parser.add_argument('--no-osc', action='store_true')
    parser.add_argument('--port', type=int, default=7000)
    args = parser.parse_args()
    run(camera_id=args.camera, show_preview=not args.no_preview, send_osc=not args.no_osc, osc_port=args.port)
