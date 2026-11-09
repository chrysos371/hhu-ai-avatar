import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "../lib/api";
import type { SystemInfo } from "../lib/types";
export function SystemStatus() {
  const q = useQuery({
    queryKey: ["system"],
    queryFn: () => apiRequest<SystemInfo>("/system"),
    refetchInterval: 30000,
  });
  return (
    <span
      className={
        "badge service-status " +
        (q.isError ? "error" : q.data?.backend.available ? "ok" : "")
      }
      role="status"
    >
      {q.isPending
        ? "读取状态…"
        : q.isError
          ? "连接异常"
          : q.data?.backend.available
            ? "后端已连接"
            : "后端不可用"}
    </span>
  );
}
