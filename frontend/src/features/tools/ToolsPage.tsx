import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { apiRequest } from "../../lib/api";
import type { Health } from "../../lib/types";
import { PageHeading, QueryState } from "../../components/QueryState";
export function ToolsPage() {
  const query = useQuery({
    queryKey: ["tools-health"],
    queryFn: () => apiRequest<Health[]>("/tools/health"),
  });
  return (
    <section>
      <PageHeading
        title="工具"
        description="只读检查已接入的服务。可连接不代表模型能力达标，未探测的服务保持未知。"
        action={
          <button
            className="button secondary"
            disabled={query.isFetching}
            onClick={() => query.refetch()}
          >
            <RefreshCw size={14} />
            重新检查
          </button>
        }
      />
      <QueryState query={query}>
        <div className="grid two">
          {query.data?.map((service) => (
            <article className="panel" key={service.name}>
              <div className="section-top">
                <h2>{service.name}</h2>
                <span
                  className={
                    "badge " +
                    (service.available === true
                      ? "ok"
                      : service.available === false
                        ? "warn"
                        : "")
                  }
                >
                  {service.available === true
                    ? "可用"
                    : service.available === false
                      ? "暂不可用"
                      : "未探测"}
                </span>
              </div>
              <p className="muted">
                {service.configured ? "已配置" : "尚未配置"}
              </p>
              <p>{service.last_error ?? "最近检查未发现连接错误。"}</p>
            </article>
          ))}
        </div>
      </QueryState>
      <p className="notice">
        密钥与代理凭据不会从管理接口返回。本地管理模型不可用时，人设等手动编辑仍可使用。
      </p>
    </section>
  );
}
