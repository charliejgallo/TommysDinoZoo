// Cartoon water: a teal surface with soft moving ripples and a light rim
// where it meets the shore (depth-based foam).
shader_type spatial;
render_mode blend_mix, cull_back, depth_draw_opaque;

uniform vec4 deep : source_color = vec4(0.22, 0.62, 0.78, 0.92);
uniform vec4 shallow : source_color = vec4(0.48, 0.86, 0.9, 0.85);
uniform sampler2D noise_tex : repeat_enable, filter_linear_mipmap;
uniform sampler2D depth_tex : hint_depth_texture, filter_linear_mipmap;

varying vec3 wpos;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	float t = TIME * 0.04;
	float n = texture(noise_tex, wpos.xz * 0.08 + vec2(t, t * 0.6)).r;
	float n2 = texture(noise_tex, wpos.xz * 0.13 - vec2(t * 0.7, t)).r;
	float rip = smoothstep(0.62, 0.7, (n + n2) * 0.5);
	float depth = texture(depth_tex, SCREEN_UV).r;
	vec4 ndc = vec4(SCREEN_UV * 2.0 - 1.0, depth, 1.0);
	vec4 view = INV_PROJECTION_MATRIX * ndc;
	view.xyz /= view.w;
	float dz = clamp((VERTEX.z - view.z) * 1.2, 0.0, 1.0);
	vec3 c = mix(shallow.rgb, deep.rgb, dz);
	float foam = 1.0 - smoothstep(0.0, 0.25, dz);
	c = mix(c, vec3(0.95, 1.0, 1.0), max(rip * 0.35, foam * 0.8));
	ALBEDO = c;
	ALPHA = mix(shallow.a, deep.a, dz);
	ROUGHNESS = 0.15;
	SPECULAR = 0.6;
}
