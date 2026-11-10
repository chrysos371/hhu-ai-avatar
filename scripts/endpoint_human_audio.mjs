import { readFileSync, writeFileSync } from 'node:fs';
import { EnergyEndpoint } from '../frontend/src/features/chat/endpointing.ts';
const manifest = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const output = process.argv[3];
for (const row of manifest.rows) {
  const audio = readFileSync(row.augmented_path);
  if (audio.toString('ascii', 36, 40) !== 'data' || audio.readUInt16LE(22) !== 1 || audio.readUInt16LE(34) !== 16)
    throw Error('Expected generated canonical mono16 WAV');
  const rate = audio.readUInt32LE(24), count = audio.readUInt32LE(40) / 2;
  const detector = new EnergyEndpoint(rate);
  let consumed = 0, reason = null;
  for (let index = 0; index < count && !reason; index += 4096) {
    const chunk = new Float32Array(Math.min(4096, count-index));
    for (let j = 0; j < chunk.length; j++) chunk[j] = audio.readInt16LE(44 + (index+j)*2) / 32768;
    const result = detector.push(chunk); consumed += result.consumed; reason = result.reason;
  }
  row.endpoint_reason = reason; row.endpoint_seconds = consumed/rate;
  row.end_minus_original_file_seconds = consumed/rate - row.duration_seconds;
  if (reason === 'pause') {
    const clip = Buffer.from(audio.subarray(0, 44 + consumed*2));
    clip.writeUInt32LE(clip.length-8, 4); clip.writeUInt32LE(consumed*2, 40);
    writeFileSync(row.cropped_path, clip, { flag: 'wx' });
  }
}
writeFileSync(output, JSON.stringify(manifest, null, 2)+'\n', { flag: 'wx' });
console.log(JSON.stringify({ total: manifest.rows.length, reasons: manifest.rows.reduce((result,row) => {
  result[row.endpoint_reason ?? 'none'] = (result[row.endpoint_reason ?? 'none'] ?? 0)+1; return result;
}, {}) }));
