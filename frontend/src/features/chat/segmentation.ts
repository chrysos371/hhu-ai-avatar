/** Keep spoken text ordered and bounded; only final reviewed replies enter this queue. */
export function splitSpeechText(text: string, limit = 160): string[] {
  const result: string[] = [];
  let buffer = "";
  for (const character of text) {
    buffer += character;
    if (buffer.length >= limit || buffer.length >= 32 && /[。！？!?\n]/.test(character)) {
      if (buffer.trim()) result.push(buffer.trim());
      buffer = "";
    }
  }
  if (buffer.trim()) result.push(buffer.trim());
  return result;
}
