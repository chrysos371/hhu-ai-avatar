import type { LipFrame } from "../../lib/types";

export function AvatarStage({ name = "角色", mouth, valence = 0, arousal = 0, busy = false, speaking = false }: {
  name?: string; mouth: LipFrame | null; valence?: number; arousal?: number; busy?: boolean; speaking?: boolean;
}) {
  const open = Math.min(1, Math.max(0, mouth?.mouth_open ?? 0));
  const round = mouth?.vowel === "o" || mouth?.vowel === "u";
  const label = busy ? "正在思考" : speaking ? "正在说话" : valence < -0.2 ? "安静陪伴" : valence > 0.2 ? "愉快陪伴" : "正在聆听";
  return <div className={"avatar-stage" + (speaking ? " speaking" : "") + (busy ? " thinking" : "")}
    role="img" aria-label={name + "，" + label} data-mouth-open={open.toFixed(3)}>
    <svg viewBox="0 0 300 260" aria-hidden="true">
      <ellipse className="avatar-aura" cx="150" cy="140" rx="116" ry="105" />
      <path fill="#253b52" d="M68 135C58 35 95 12 150 12s92 23 82 123l-18 61H86z" />
      <path fill="#456f88" d="M58 260q10-78 92-78t92 78" />
      <path fill="#b0d8df" d="m118 184 32 29 32-29 13 76h-90z" />
      <path fill="#f5dbc7" d="M80 80q0-47 70-47t70 47v50c0 43-32 65-70 65s-70-22-70-65z" />
      <path fill="#253b52" d="M72 96q-5-75 78-75t78 75q-49-11-61-48-28 37-95 48" />
      <g className="avatar-eyes" style={{ transformOrigin: "150px 117px" }}>
        <path d={valence > 0.2 ? "M104 119q12-17 24 0M172 119q12-17 24 0" : "M104 115q12-7 24 0M172 115q12-7 24 0"} fill="none" stroke="#253b52" strokeWidth="5" strokeLinecap="round" />
        {valence <= 0.2 && <><ellipse cx="116" cy="120" rx="5" ry={6 + Math.max(0, arousal) * 2} fill="#253b52" /><ellipse cx="184" cy="120" rx="5" ry={6 + Math.max(0, arousal) * 2} fill="#253b52" /></>}
      </g>
      <ellipse cx="103" cy="139" rx="12" ry="5" fill="#e9a4a0" opacity=".5" />
      <ellipse cx="197" cy="139" rx="12" ry="5" fill="#e9a4a0" opacity=".5" />
      {open > 0.04 ? <ellipse cx="150" cy="156" rx={round ? 7 + open * 5 : 11 + open * 7} ry={2 + open * 15} fill="#824c51" />
        : <path d={valence < -0.2 ? "M140 158q10-6 20 0" : "M138 153q12 9 24 0"} fill="none" stroke="#a06465" strokeWidth="3" strokeLinecap="round" />}
      <path d="m141 218 9 12 9-12-9-7z" fill="#78bdcd" />
    </svg>
    <span className="avatar-caption"><i />{label}</span>
  </div>;
}
