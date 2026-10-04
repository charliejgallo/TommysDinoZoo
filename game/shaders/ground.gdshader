// Ground: vertex colours painted by the world (grass, paths, zones) with a
// little noise so big lawns don't look flat, under the same soft two-band
// light as the toon shader.
shader_type spatial;

uniform sampler2D noise_tex : repeat_enable, filter_linear_mipmap;
uniform sampler2D color_tex : source_color, filter_linear;
uniform float noise_amt = 0.08;
uniform float band_soft = 0.22;
uniform float shade = 0.5;
uniform vec3 shade_tint : source_color = vec3(0.78, 0.82, 1.0);

varying vec3 wpos;

void vertex() {
	wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	float n = texture(noise_tex, wpos.xz * 0.045).r;
	float n2 = texture(noise_tex, wpos.xz * 0.37).r;
	vec3 c = texture(color_tex, UV).rgb * (1.0 + (n - 0.5) * noise_amt * 2.0 + (n2 - 0.5) * noise_amt);
	ALBEDO = c;
	ROUGHNESS = 0.95;
	SPECULAR = 0.1;
}

void light() {
	float ndl = dot(NORMAL, LIGHT);
	float band = smoothstep(0.0, band_soft, ndl) * ATTENUATION;
	vec3 l = mix(shade_tint * shade, vec3(1.0), band);
	DIFFUSE_LIGHT += l * LIGHT_COLOR * ALBEDO / PI;
}
