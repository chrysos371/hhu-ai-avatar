// Node >=22.12 with --experimental-strip-types. Uses frozen fixtures, no microphone.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { EnergyEndpoint } from '../frontend/src/features/chat/endpointing.ts';
const protocolPath = 'evals/interaction/cycle-02/endpointing-protocol.json';
const protocolBytes = readFileSync(protocolPath);
const protocol = JSON.parse(protocolBytes);
const output = process.argv[2];
if (!output) throw Error('Pass new output JSON path');
const rows = [];
for (const rate of protocol.rates) for (const chunkSize of protocol.chunkSizes) for (const test of protocol.cases) {
  let seed = protocol.seed;
  const chunks = test.segments.map(([kind, ms, amplitude = 0]) => {
    const data = new Float32Array(Math.round(rate * ms / 1000));
    for (let i = 0; i < data.length; i++) {
      seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
      data[i] = kind === 'tone' ? amplitude * Math.sin(2 * Math.PI * 220 * i / rate)
        : kind === 'noise' ? amplitude * ((seed / 4294967296) * 2 - 1) : 0;
    }
    return data;
  });
  const all = new Float32Array(chunks.reduce((n, c) => n + c.length, 0));
  let offset = 0;
  for (const chunk of chunks) { all.set(chunk, offset); offset += chunk.length; }
  const endpoint = new EnergyEndpoint(rate, protocol.parameters);
  let reason = null;
  for (let i = 0; i < all.length && !reason; i += chunkSize) reason = endpoint.push(all.subarray(i, i + chunkSize)).reason;
  const errorMs = Math.abs(endpoint.elapsedMs - test.targetMs);
  rows.push({ id: test.id, rate, chunkSize, reason, endMs: endpoint.elapsedMs, errorMs,
    expected: test.expected, knownLimitation: test.limitation ?? null,
    pass: reason === test.expected && errorMs <= protocol.gates.maxAbsoluteTimingErrorMs });
}
const result = { sourceHead: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
  protocolSha256: createHash('sha256').update(protocolBytes).digest('hex'),
  implementationSha256: createHash('sha256').update(readFileSync('frontend/src/features/chat/endpointing.ts')).digest('hex'),
  rows, passed: rows.filter(x => x.pass).length, total: rows.length,
  maxErrorMs: Math.max(...rows.map(x => x.errorMs)), limitations: protocol.scope };
writeFileSync(output, JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
console.log(JSON.stringify({ passed: result.passed, total: result.total, maxErrorMs: result.maxErrorMs }));
if (result.passed !== result.total) process.exitCode = 1;
