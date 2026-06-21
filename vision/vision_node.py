"""
vision/vision_node.py
Wires the YOLOv8 + ByteTrack vision pipeline to the ZeroMQ message bus.
Reads from camera/video, processes frames, and publishes live events.
"""
import argparse
import json
import time
import cv2
import zmq
from loguru import logger

import config.logging_config  # setup loguru
from config.settings import settings
from vision.stream_reader import StreamReader
from vision.detector import Detector
from vision.tracker import Tracker
from vision.violation_detector import ViolationDetector
from vision.accident_detector import AccidentDetector
from vision.congestion_map import CongestionMap


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=str, default="0", help="Camera source (0, or video.mp4)")
    parser.add_argument("--intersection", type=str, default="INT_1", help="Intersection ID")
    parser.add_argument("--show", action="store_true", help="Show video window")
    args = parser.parse_args()

    # 1. ZeroMQ Publisher setup
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(settings.ZMQ_BROKER_FRONTEND)
    logger.info(f"Vision Node connected to ZMQ broker at {settings.ZMQ_BROKER_FRONTEND}")
    time.sleep(1)  # allow connection to settle

    # 2. Vision Pipeline Initialization
    reader = StreamReader([int(args.source) if args.source.isdigit() else args.source])
    fps = reader.fps
    detector = Detector()
    tracker = Tracker(fps=int(fps))
    
    violation_detector = ViolationDetector(args.intersection, publisher=pub)
    accident_detector = AccidentDetector(args.intersection, publisher=pub)
    congestion_map = CongestionMap(args.intersection)

    # We need to know the current signal phase to detect red-light runners.
    # In a full system, we would subscribe to signals.INT_1. For the vision node, 
    # we'll assume a dummy state if we aren't subscribed, or just rely on ZMQ state.
    # To keep it simple and stateless, we pass a dummy {"N": "GREEN", ...} 
    # or rely on the signal_agent pushing it to Redis. For now, we pass dummy.
    dummy_signal_phase = {"N": "GREEN", "S": "GREEN", "E": "RED", "W": "RED"}

    logger.info(f"Starting vision loop for {args.intersection}...")
    last_pub_time = time.time()

    try:
        while True:
            frames = reader.read_all()
            if not frames or frames[0] is None:
                # Video ended or camera disconnected
                if not str(args.source).isdigit():
                    break
                time.sleep(0.1)
                continue

            frame = frames[0]

            # Detect & Track
            boxes = detector.detect(frame)
            tracked_boxes = tracker.update(boxes)

            # Gather speeds and directions
            speeds = {}
            directions = {}
            for box in tracked_boxes:
                if box.track_id is not None:
                    speeds[box.track_id] = tracker.get_speed_kmh(box.track_id)
                    directions[box.track_id] = tracker.get_direction(box.track_id)

            # Heuristics
            violation_detector.check_all(frame, tracked_boxes, speeds, directions, dummy_signal_phase)
            accident_detector.update(tracked_boxes, speeds)
            
            # Congestion
            state = congestion_map.compute(tracked_boxes, speeds)

            # Publish congestion state once per second
            now = time.time()
            if now - last_pub_time >= 1.0:
                payload = {
                    "intersection_id": args.intersection,
                    "level": state.level,
                    "queue_lengths": state.queue_lengths,
                    "total_vehicles": state.total_vehicles,
                    "pedestrians_waiting": state.pedestrians_waiting
                }
                pub.send_string(f"congestion.{args.intersection} {json.dumps(payload)}")
                last_pub_time = now

            if args.show:
                # Draw boxes for debugging
                for box in tracked_boxes:
                    x1, y1, x2, y2 = box.x1, box.y1, box.x2, box.y2
                    tid = box.track_id
                    spd = speeds.get(tid, 0.0)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"ID:{tid} {spd:.1f}km/h", (x1, y1 - 10), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                cv2.imshow("Vision Node", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        logger.info("Vision node interrupted.")
    finally:
        reader.release()
        cv2.destroyAllWindows()
        pub.close()
        ctx.term()

if __name__ == "__main__":
    main()
