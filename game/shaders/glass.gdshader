// Cartoon glass for materials exported with alpha (role `glass`: the
// incubator dome, windows that should show what is behind). Pale tint,
// more opaque at grazing angles, a crisp highlight. Picked by look.gd for
// any glTF material with transparency; `fade` matches toon.gdshader.
shader_type spatial;
render_mode blend_mix, cull_back, depth_draw_opaque;

uniform vec4 albedo : source_color = vec4(0.83, 0.95, 0.98, 0.45);
uniform float fade = 0.0;
uniform float tint_mix = 0.0;
uniform vec4 tint : source_color = vec4(1.0);

void fragment() {
	float fres = 1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0);
	vec3 c = mix(albedo.rgb, tint.rgb, tint_mix);
	ALBEDO = c;
	ALPHA = clamp(albedo.a * (0.55 + 1.1 * pow(fres, 2.0)), 0.0, 0.95) * (1.0 - fade);
	ROUGHNESS = 0.12;
	SPECULAR = 0.7;
	EMISSION = c * 0.12 * pow(fres, 2.0);
}
