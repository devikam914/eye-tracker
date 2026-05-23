# -*- coding: utf-8 -*-
"""
Robust Camera Calibration Script
=================================
1. Generates a checkerboard image you can display on your phone/tablet
2. Auto-captures frames when the board is detected and stable
3. Rejects blurry or low-quality frames automatically
4. Shows per-frame reprojection error and rejects outliers
5. Saves camera params in ptgaze-compatible format

Usage:
  python get_camera_params.py

Instructions:
  - Display the generated 'checkerboard.png' on your phone or print it
  - Hold it in front of your webcam at different angles and distances
  - The script auto-captures when the board is stable (green border = captured)
  - Move the board to different positions after each capture
  - Press Q when you have 20+ captures (more = better)
  - Press ESC to abort
"""

import cv2
import numpy as np
import os
import sys
import yaml

# ── Configuration ──────────────────────────────────────────────────────────────
CHECKERBOARD       = (9, 6)       # inner corners (cols, rows)
SQUARE_SIZE_MM     = 25.0         # only matters if you need real-world scale
MIN_FRAMES         = 15
TARGET_FRAMES      = 25
BLUR_THRESHOLD     = 80.0         # Laplacian variance below this = blurry
STABILITY_FRAMES   = 8            # corners must be stable for N frames
STABILITY_PX       = 2.5          # max corner movement (px) to count as stable
REPROJ_ERR_MAX     = 1.0          # reject frames with reproj error > this
AUTO_CAPTURE_DELAY = 1.5          # seconds between auto-captures
OUTPUT_FILE        = "my_camera_params.yaml"

# ── Step 0: Generate checkerboard image ───────────────────────────────────────
def generate_checkerboard(cols, rows, square_px=80):
    """Generate a checkerboard PNG to display on phone/tablet."""
    # We need (cols+1) x (rows+1) squares to get (cols x rows) inner corners
    board_w = (cols + 1) * square_px
    board_h = (rows + 1) * square_px
    # Add white border
    border = square_px
    img = np.ones((board_h + 2*border, board_w + 2*border), dtype=np.uint8) * 255
    for r in range(rows + 1):
        for c in range(cols + 1):
            if (r + c) % 2 == 1:
                x0 = border + c * square_px
                y0 = border + r * square_px
                img[y0:y0+square_px, x0:x0+square_px] = 0
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "checkerboard.png")
    cv2.imwrite(path, img)
    return path


def compute_blur(gray_frame):
    """Laplacian variance — higher = sharper."""
    return cv2.Laplacian(gray_frame, cv2.CV_64F).var()


def corners_stable(prev_corners, curr_corners, threshold_px):
    """Check if corners haven't moved much between frames."""
    if prev_corners is None or curr_corners is None:
        return False
    if prev_corners.shape != curr_corners.shape:
        return False
    diff = np.abs(prev_corners - curr_corners).max()
    return diff < threshold_px


def compute_per_frame_error(objpoints, imgpoints, rvecs, tvecs, mtx, dist):
    """Compute reprojection error for each frame."""
    errors = []
    for i in range(len(objpoints)):
        projected, _ = cv2.projectPoints(objpoints[i], rvecs[i], tvecs[i], mtx, dist)
        err = cv2.norm(imgpoints[i], projected, cv2.NORM_L2) / len(projected)
        errors.append(err)
    return errors


def main():
    # Generate checkerboard
    cb_path = generate_checkerboard(CHECKERBOARD[0], CHECKERBOARD[1])
    print(f"Checkerboard saved to: {cb_path}")
    print(f"Display this on your phone/tablet, or print it.")
    print()

    # Prepare 3D object points
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    objp = np.zeros((CHECKERBOARD[0] * CHECKERBOARD[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHECKERBOARD[0], 0:CHECKERBOARD[1]].T.reshape(-1, 2)
    objp *= SQUARE_SIZE_MM

    objpoints = []  # 3D points
    imgpoints = []  # 2D points
    frame_previews = []  # for visualization

    # Open camera
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Camera not detected")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    print("="*60)
    print("  CAMERA CALIBRATION")
    print("="*60)
    print(f"  Target: {TARGET_FRAMES} frames (minimum {MIN_FRAMES})")
    print(f"  Auto-capture when board is stable")
    print(f"  Move board to different angles/distances after each capture")
    print(f"  Press Q when done (after {MIN_FRAMES}+ frames)")
    print(f"  Press ESC to abort")
    print("="*60)
    print()

    prev_corners = None
    stable_count = 0
    last_capture_time = 0
    captured_count = 0
    flash_timer = 0  # green flash on capture

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        display = frame.copy()
        h, w = frame.shape[:2]
        now = cv2.getTickCount() / cv2.getTickFrequency()

        # Detect checkerboard
        found, corners = cv2.findChessboardCorners(
            gray, CHECKERBOARD,
            cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE + cv2.CALIB_CB_FAST_CHECK
        )

        blur_val = compute_blur(gray)
        is_sharp = blur_val > BLUR_THRESHOLD

        if found:
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

            # Check stability
            if corners_stable(prev_corners, corners2, STABILITY_PX):
                stable_count += 1
            else:
                stable_count = 0
            prev_corners = corners2.copy()

            is_stable = stable_count >= STABILITY_FRAMES
            time_ok = (now - last_capture_time) > AUTO_CAPTURE_DELAY

            # Auto-capture if stable + sharp + enough time passed
            if is_stable and is_sharp and time_ok:
                objpoints.append(objp.copy())
                imgpoints.append(corners2)
                captured_count += 1
                last_capture_time = now
                stable_count = 0
                flash_timer = 15  # frames of green flash
                print(f"  [AUTO-CAPTURE {captured_count}]"
                      f"  blur={blur_val:.0f}"
                      f"  {'SHARP' if is_sharp else 'BLURRY'}")

            # Draw detected corners
            cv2.drawChessboardCorners(display, CHECKERBOARD, corners2, found)

            # Status color
            if is_stable and is_sharp:
                status_color = (0, 255, 0)  # green = ready to capture
                status_text = "STABLE - capturing..."
            elif not is_sharp:
                status_color = (0, 165, 255)  # orange = blurry
                status_text = f"BLURRY (hold still, blur={blur_val:.0f})"
            else:
                status_color = (0, 255, 255)  # yellow = stabilizing
                pct = min(100, int(100 * stable_count / STABILITY_FRAMES))
                status_text = f"STABILIZING... {pct}%"
        else:
            prev_corners = None
            stable_count = 0
            status_color = (0, 0, 255)  # red = no board
            status_text = "No checkerboard detected"

        # Green flash on capture
        if flash_timer > 0:
            cv2.rectangle(display, (0, 0), (w-1, h-1), (0, 255, 0), 8)
            flash_timer -= 1

        # Draw UI
        # Top bar
        cv2.rectangle(display, (0, 0), (w, 50), (30, 30, 30), -1)
        cv2.putText(display, status_text, (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, status_color, 2)

        # Progress
        progress_text = f"Captured: {captured_count}/{TARGET_FRAMES}"
        if captured_count >= MIN_FRAMES:
            progress_text += "  [Press Q to finish]"
        cv2.putText(display, progress_text, (10, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        # Progress bar
        bar_w = w - 20
        bar_h = 6
        bar_y = h - 15
        cv2.rectangle(display, (10, bar_y), (10 + bar_w, bar_y + bar_h), (60, 60, 60), -1)
        fill = int(bar_w * min(captured_count / TARGET_FRAMES, 1.0))
        bar_color = (0, 220, 80) if captured_count >= MIN_FRAMES else (0, 180, 255)
        cv2.rectangle(display, (10, bar_y), (10 + fill, bar_y + bar_h), bar_color, -1)

        # Blur meter (bottom-left)
        blur_text = f"Sharpness: {blur_val:.0f}"
        blur_color = (0, 220, 80) if is_sharp else (0, 80, 255)
        cv2.putText(display, blur_text, (10, h - 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, blur_color, 1)

        cv2.imshow("Camera Calibration", display)
        key = cv2.waitKey(1) & 0xFF

        if key == 27:  # ESC
            print("Aborted.")
            cap.release()
            cv2.destroyAllWindows()
            sys.exit(0)
        elif key == ord('q') or key == ord('Q'):
            if captured_count >= MIN_FRAMES:
                break
            else:
                print(f"  Need at least {MIN_FRAMES} frames. Currently: {captured_count}")

    cap.release()
    cv2.destroyAllWindows()

    print()
    print(f"Captured {captured_count} frames. Calibrating...")

    # ── Calibrate ──────────────────────────────────────────────────────────────
    ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
        objpoints, imgpoints, gray.shape[::-1], None, None)

    # ── Per-frame error & outlier rejection ────────────────────────────────────
    errors = compute_per_frame_error(objpoints, imgpoints, rvecs, tvecs, mtx, dist)

    print()
    print("Per-frame reprojection errors:")
    good_obj, good_img = [], []
    for i, err in enumerate(errors):
        status = "OK" if err < REPROJ_ERR_MAX else "REJECTED"
        marker = "  " if err < REPROJ_ERR_MAX else ">>"
        print(f"  {marker} Frame {i+1:2d}: {err:.4f}px [{status}]")
        if err < REPROJ_ERR_MAX:
            good_obj.append(objpoints[i])
            good_img.append(imgpoints[i])

    rejected = len(objpoints) - len(good_obj)
    if rejected > 0:
        print(f"\nRejected {rejected} frame(s) with high error. Re-calibrating with {len(good_obj)} frames...")
        if len(good_obj) < MIN_FRAMES:
            print(f"WARNING: Only {len(good_obj)} good frames remain. Results may be less accurate.")
        if len(good_obj) >= 6:
            ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
                good_obj, good_img, gray.shape[::-1], None, None)
        else:
            print("ERROR: Not enough good frames for calibration. Please try again.")
            sys.exit(1)

    # ── Results ────────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  CALIBRATION RESULTS")
    print("=" * 60)
    print(f"  Frames used:       {len(good_obj)}")
    print(f"  Reproj error:      {ret:.4f}px" +
          (" (GOOD)" if ret < 0.5 else " (OK)" if ret < 1.0 else " (HIGH - consider recalibrating)"))
    print(f"  Focal length:      fx={mtx[0,0]:.1f}  fy={mtx[1,1]:.1f}")
    print(f"  Principal point:   cx={mtx[0,2]:.1f}  cy={mtx[1,2]:.1f}")
    print(f"  Distortion:        {np.round(dist.ravel(), 4)}")
    print("=" * 60)

    # ── Compare with generic params ────────────────────────────────────────────
    print()
    print("Comparison with generic params (sample_params.yaml):")
    print(f"  fx: 640.0 -> {mtx[0,0]:.1f}  (diff: {abs(mtx[0,0]-640):.1f}px)")
    print(f"  fy: 640.0 -> {mtx[1,1]:.1f}  (diff: {abs(mtx[1,1]-640):.1f}px)")
    print(f"  cx: 320.0 -> {mtx[0,2]:.1f}  (diff: {abs(mtx[0,2]-320):.1f}px)")
    print(f"  cy: 240.0 -> {mtx[1,2]:.1f}  (diff: {abs(mtx[1,2]-240):.1f}px)")

    # ── Save ───────────────────────────────────────────────────────────────────
    params = {
        'image_height': int(gray.shape[0]),
        'image_width':  int(gray.shape[1]),
        'camera_matrix': {
            'rows': 3, 'cols': 3,
            'data': mtx.ravel().tolist()
        },
        'distortion_coefficients': {
            'rows': 1, 'cols': 5,
            'data': dist.ravel().tolist()
        }
    }

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), OUTPUT_FILE)
    with open(out_path, 'w') as f:
        yaml.dump(params, f, default_flow_style=False)

    print()
    print(f"Saved to: {out_path}")
    print("You can now run main.py — it will use these camera params.")
    print()


if __name__ == "__main__":
    main()