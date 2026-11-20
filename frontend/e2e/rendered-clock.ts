/** The registered oracle uses vowel a; this checks the actual presentation,
 * retaining SVG geometry while adding the Three render/source observations. */
export type RenderedClock = {
  renderer: string; modelTime: number | null; modelMappedTime: number | null;
  modelOpen: number | null; modelHeight: number | null; modelRenders: number | null;
  modelContextLost: boolean | null;
};
function finite(value: number | null): value is number {
  return value !== null && Number.isFinite(value);
}
export function renderedGeometry(row: RenderedClock, open: string, radius: number | null) {
  if (row.renderer === 'ready') {
    if (!finite(row.modelOpen) || !finite(row.modelHeight) || !finite(row.modelTime)
        || !finite(row.modelMappedTime) || !finite(row.modelRenders)) return false;
    const height = row.modelOpen <= .01 ? .018 : .025 + row.modelOpen * .19;
    // mouthOpen is rounded to 3 decimals and mesh height to 4: the combined
    // quantization error is at most .000095 + .00005 world units.
    return row.modelOpen >= 0 && row.modelOpen <= 1 && row.modelRenders > 0
      && row.modelContextLost === false && Math.abs(row.modelTime - row.modelMappedTime) <= 1e-6
      && Math.abs(row.modelHeight - height) <= .00015;
  }
  return ['loading', 'fallback', 'lost'].includes(row.renderer)
    && (Number(open) <= .04 ? radius === null
      : radius !== null && Math.abs(radius - (2 + Number(open) * 15)) <= .01);
}
export function renderedLag(row: RenderedClock, mediaTime: number, svgLag: number | null) {
  return row.renderer === 'ready'
    ? finite(row.modelTime) ? (mediaTime - row.modelTime) * 1000 : null
    : svgLag;
}
