class_name Stage
## Shared environment pieces: sky, sun, ambient, fog and the "miniature"
## tilt-shift blur, plus the game's 3/4 camera numbers. Used by the game
## world and by the model viewer, so models are judged under the real light.

const CAM_PITCH := 48.0      # degrees down from horizontal
const CAM_DIST := 14.0       # metres from the target
const CAM_FOV := 30.0

static func make_env(parent: Node) -> Dictionary:
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var psm := ProceduralSkyMaterial.new()
	psm.sky_top_color = Color(0.42, 0.66, 0.95)
	psm.sky_horizon_color = Color(0.82, 0.9, 0.97)
	psm.ground_horizon_color = Color(0.82, 0.9, 0.97)
	psm.ground_bottom_color = Color(0.5, 0.6, 0.45)
	sky.sky_material = psm
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.3
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.tonemap_exposure = 1.0
	env.tonemap_white = 4.0
	env.ssao_enabled = true
	env.ssao_radius = 0.6
	env.ssao_intensity = 1.2
	env.glow_enabled = true
	env.glow_intensity = 0.25
	env.glow_bloom = 0.04
	env.adjustment_enabled = true
	env.adjustment_saturation = 1.05
	var we := WorldEnvironment.new()
	we.environment = env
	var ca := CameraAttributesPractical.new()
	ca.dof_blur_far_enabled = true
	ca.dof_blur_far_distance = CAM_DIST + 7.0
	ca.dof_blur_far_transition = 10.0
	ca.dof_blur_near_enabled = true
	ca.dof_blur_near_distance = CAM_DIST - 5.0
	ca.dof_blur_near_transition = 3.0
	ca.dof_blur_amount = 0.03
	we.camera_attributes = ca
	parent.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.light_color = Color(1.0, 0.96, 0.88)
	sun.light_energy = 1.0
	sun.shadow_enabled = true
	sun.shadow_blur = 1.5
	sun.directional_shadow_max_distance = 40.0
	sun.rotation_degrees = Vector3(-55, -35, 0)
	parent.add_child(sun)
	return {"env": env, "sun": sun, "world_env": we}

static func cam_offset() -> Vector3:
	var p := deg_to_rad(CAM_PITCH)
	return Vector3(0, sin(p), cos(p)) * CAM_DIST

static func place_camera(cam: Camera3D, target: Vector3) -> void:
	cam.fov = CAM_FOV
	cam.global_position = target + cam_offset()
	cam.look_at(target, Vector3.UP)
