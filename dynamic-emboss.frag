#ifdef GL_ES
precision highp float;
#endif

uniform sampler2D uHeightMap;
uniform sampler2D uMaskMap;
uniform vec2 uResolution;
uniform vec2 uPosition;
uniform float uH;
uniform float uRadius;
uniform float uBaseHeight;
uniform float uCutoutMode;

varying vec2 vUv;

float embossMask(vec2 uv) {
  return texture2D(uMaskMap, uv).r;
}

float localBoost(vec2 uv) {
  vec2 aspect = vec2(uResolution.x / uResolution.y, 1.0);
  float d = distance(uv * aspect, uPosition * aspect);
  float t = smoothstep(uRadius, 0.0, d);
  return t * t * (3.0 - 2.0 * t);
}

float heightAt(vec2 uv) {
  float base = texture2D(uHeightMap, uv).r * embossMask(uv);
  float baseHeight = uBaseHeight > 0.0 ? uBaseHeight : 0.55;

  // This heightens the existing ornament around uPosition without raising
  // the flat paper/background areas.
  return base * (baseHeight + uH * localBoost(uv));
}

vec3 normalAt(vec2 uv) {
  vec2 px = 1.0 / uResolution;
  float l = heightAt(uv - vec2(px.x, 0.0));
  float r = heightAt(uv + vec2(px.x, 0.0));
  float d = heightAt(uv - vec2(0.0, px.y));
  float u = heightAt(uv + vec2(0.0, px.y));
  return normalize(vec3((l - r) * 8.0, (d - u) * 8.0, 1.0));
}

void main() {
  vec3 n = normalAt(vUv);
  vec3 light = normalize(vec3(-0.45, 0.55, 0.72));
  float diffuse = dot(n, light) * 0.5 + 0.5;
  float cavity = heightAt(vUv) * (1.0 - diffuse);
  float rim = pow(1.0 - max(dot(n, vec3(0.0, 0.0, 1.0)), 0.0), 1.8);

  vec3 greyPaper = vec3(0.70);
  vec3 color = greyPaper * (0.74 + diffuse * 0.34);
  color += vec3(0.28) * rim;
  color -= vec3(0.20) * cavity;
  color = mix(color, vec3(0.0), uCutoutMode * (1.0 - smoothstep(0.10, 0.55, embossMask(vUv))));

  gl_FragColor = vec4(color, 1.0);
}
