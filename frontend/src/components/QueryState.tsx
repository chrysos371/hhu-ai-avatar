import type { ReactNode } from "react";
export function QueryState({
  query,
  children,
}: {
  query: {
    isPending: boolean;
    isError: boolean;
    error: Error | null;
    refetch: () => unknown;
  };
  children: ReactNode;
}) {
  if (query.isPending)
    return (
      <div className="panel empty" role="status">
        正在读取真实状态…
      </div>
    );
  if (query.isError)
    return (
      <div className="error-box" role="alert">
        <p>{query.error?.message ?? "暂时无法读取数据。"}</p>
        <button className="button secondary" onClick={() => query.refetch()}>
          重新读取
        </button>
      </div>
    );
  return <>{children}</>;
}
export function PageHeading({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <p className="eyebrow">MISSION CONTROL</p>
        <h1>{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {action}
    </div>
  );
}
export function ErrorMessage({ error }: { error: Error | null }) {
  return error ? (
    <div className="error-box" role="alert">
      {error.message}
    </div>
  ) : null;
}
