export function displayValue(value: unknown) {
  return value === null || value === undefined
    ? "—"
    : typeof value === "object"
      ? JSON.stringify(value, null, 2)
      : String(value);
}
export function PersonaDiff({
  diff,
}: {
  diff: { field: string; before: unknown; after: unknown }[];
}) {
  return (
    <div>
      {diff.map((d) => (
        <article key={d.field} style={{ marginBottom: 14 }}>
          <h3>{d.field}</h3>
          <div className="diff">
            <div className="before">
              <small>当前值</small>
              <pre>{displayValue(d.before)}</pre>
            </div>
            <div className="after">
              <small>确认后</small>
              <pre>{displayValue(d.after)}</pre>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
