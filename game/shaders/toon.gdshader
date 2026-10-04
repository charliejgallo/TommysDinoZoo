// Soft cartoon look shared by every model: two soft light bands, a warm
// sunlit side, a cool shade side, and a dark rim at grazing angles that
// separates shapes (the "clay toy" look). Colours come from the glTF
// material's base colour (copied in by look.gd).
shader_type spatial;
render_mode cull_back;

uniform vec4 albedo : source_color = vec4(1.0);
uniform float rim_dark = 0.28;
uniform float rim_power = 2.6;
uniform float band_soft = 0.22;
uniform float shade = 0.42;          // light left in the shade band
uniform vec3 shade_tint : source_color = vec3(0.78, 0.82, 1.0);
uniform float emit = 0.0;
uniform float spec = 0.18;
uniform float tint_mix = 0.0;        // runtime recolour (palette swaps)
uniform vec4 tint : source_color = vec4(1.0);
uniform float fade = 0.0;            // 0 solid .. 1 gone (dithered)

void fragment() {
	vec3 c = mix(albedo.rgb, tint.rgb, tint_mix);
	float fres = 1.0 - clamp(dot(NORMAL, VIEW), 0.0, 1.0);
	c *= 1.0 - rim_dark * pow(fres, rim_power);
	if (fade > 0.0) {
		ivec2 q = ivec2(FRAGCOORD.xy) % 4;
		int b[16] = int[](0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5);
		if (float(b[q.y * 4 + q.x]) / 16.0 < fade) discard;
	}
	ALBEDO = c;
	ROUGHNESS = 0.7;
	SPECULAR = 0.3;
	EMISSION = c * emit;

}

void light() {
	float ndl = dot(NORMAL, LIGHT);
	float band = smoothstep(0.0, band_soft, ndl) * ATTENUATION;
	vec3 l = mix(shade_tint * shade, vec3(1.0), band);
	DIFFUSE_LIGHT += l * LIGHT_COLOR * ALBEDO / PI;
	vec3 h = normalize(VIEW + LIGHT);
	float s = pow(clamp(dot(NORMAL, h), 0.0, 1.0), 48.0);
	SPECULAR_LIGHT += smoothstep(0.5, 0.6, s) * spec * LIGHT_COLOR * ATTENUATION;
}
