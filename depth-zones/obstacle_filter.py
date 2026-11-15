"""
Filters raw RealSense D435i depth frames (in meters) using IMU pitch to :
1. Remove the ground plane (floor) without cropping the bottom of the image
2. Preserve vertical walls all the way down to the baseboard.
3. Ignore close-range hands/cane handles in the user's 3D "ego-pocket"
4. Optionally mask out white cane / hand detections from YOLO
"""

import numpy as np

class ObstacleDepthFilter:
    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        fy: float = 382.0,
        cy: float = 240.0,
        cam_height_m: float = 1.35,
        floor_clearance_m: float = 0.10,
        ego_dist_m: float = 0.45,
        ego_drop_m: float = 0.20,
    ):

        """
        Parameters:
            width, height: Depth stream resolution (default 640x480)
            fy,cy: D435i depth vertical focal length and principal point.
            cam_height_m: Approximate height of camera above the floor in meters.
            floor_clearance_m: Height buffer above floor to ignore (0.10m = 10cm)
            ego_dist_m: Distance in front of torso where hands/cane handle are ignored.
            ego_drop_m: Vertical drop below camera where the ego-pocket starts.
        """

        self.width = width
        self.height = height
        self.cam_height_m = cam_height_m
        self.floor_clearance_m = floor_clearance_m
        self.ego_dist_m = ego_dist_m
        self.ego_drop_m = ego_drop_m


        # Precompute normalized vertical pixel coordinate column: (v - cy) / fy
        v_coords = np.arange(height, dtype=np.float32).reshape(-1,1)
        self.v_norm = (v_coords - cy) / fy      # Shape : (H,1)

    def filter_frame(
        self,
        depth_m: np.ndarray,
        pitch_deg: float = 0.0,
        yolo_mask: np.ndarray = None,
        yolo_boxes: list = None,
    ) -> np.ndarray:
        """
        Takes a raw depth map (in meters) and returns a cleaned horizontal distance
        map where floor, hands, and cane pixels are set to 0.0.
        """

        if depth_m.shape != (self.height, self.width):
            raise ValueError(
                f"Expected depth_m shape {(self.height, self.width)}, got {depth_m.shape}"
            )
        
        # Convert IMU Pitch to radians (positive pitch_deg = camera tilted downward)
        theta = np.deg2rad(float(pitch_deg))
        cos_t = np.cos(theta)
        sin_t = np.sin(theta)

        # 1. Camera-frame vertical offset Y_c (positive downward)
        y_cam = self.v_norm * depth_m

        # 2. Gravity-aligned vertical drop (y_down) and true horizontal distance (z_horiz)
        y_down = y_cam * cos_t + depth_m * sin_t
        z_horiz = depth_m * cos_t - y_cam * sin_t

        # 3. Wall Preservation check: vertical walls have near-zero change in z_horiz
        # across a 5-pixel vertical step, whereas floors change distance rapidly.
        dz_dv = np.zeros_like(z_horiz)
        dz_dv[5:, :] = np.abs(z_horiz[5:, :] - z_horiz[:-5, :])
        is_vertical_wall = (dz_dv < 0.06) & (depth_m > 0)

        # 4. Identify floor pixels : near ground level AND not a vertical wall face
        floor_threshold = self.cam_height_m - self.floor_clearance_m
        is_floor = (y_down > floor_threshold) & (~is_vertical_wall)

        # 5. Identify 3D "ego-pocket" (user's own hands / cane handle close to torso)
        is_ego_hand = (
            (z_horiz > 0)
            & (z_horiz < self.ego_dist_m)
            & (y_down > self.ego_drop_m)
        )

        # Keep valid obstacle pixels; zero out floor and close hands
        valid_obstacle = (depth_m > 0) & (~is_floor) & (~is_ego_hand)
        clean_depth = np.where(valid_obstacle, z_horiz, 0.0).astype(np.float32)

        # 6. Optional YOLO masking (for once custom YOLO model is trained)
        if yolo_mask is not None:
            clean_depth[yolo_mask > 0] = 0.0
        elif yolo_boxes:
            for box in yolo_boxes:
                x1, y1, x2, y2 = [int(v) for v in box]
                x1, y1 = max(0,x1), max(0,y1)
                x2, y2 = min(self.width, x2), min(self.height, y2)
                roi = clean_depth[y1:y2, x1:x2]
                valid = roi[(roi > 0.1) & (roi < 1.5)]
                if valid.size > 20:
                    fg_depth = np.percentile(valid,15)
                    # Zero out foreground cane/hand, preserve walls behind it
                    roi[roi <= fg_depth + 0.18] = 0.0

        return clean_depth
    
# Quick test to rum from terminal
if __name__ == "__main__":
    flt = ObstacleDepthFilter(width=640, height=480, cam_height_m=1.35)

    # Create a fake scene: flat wall 1.2m left, open floor on right
    test_depth = np.zeros((480,640), dtype=np.float32)
    test_depth[:, :320] = 1.20 # Left half: vertical wall 1.2m away

    # Simulate flat floor on right half
    for v in range(260,480):
        test_depth[v, 320:] = 1.35 / flt.v_norm[v,0]

    # Simulate a hand holding a cane at 0.35m in front of chest
    test_depth[350:420, 280:360] = 0.35

    cleaned = flt.filter_frame(test_depth, pitch_deg = 0.0)

    wall_kept = np.count_nonzero(cleaned[400:470, :250])
    floor_left = np.count_nonzero(cleaned[400:470, 380:])
    hand_left = np.count_nonzero(cleaned[350:420, 280:360])

    print(f"Bottom-of-frame wall pixels kept: {wall_kept} (should be > 0)")
    print(f"Floor pixels remaining:           {floor_left} (should be 0)")
    print(f"Close hand pixels remaining:      {hand_left} (should be 0)")
    

