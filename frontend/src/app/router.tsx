import { createBrowserRouter } from "react-router-dom";
import { AppShell } from "./AppShell";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { ChatPage } from "../features/chat/ChatPage";
import { PersonaPage } from "../features/persona/PersonaPage";
import { lazy, Suspense } from "react";
const EmotionPage = lazy(() =>
  import("../features/emotion/EmotionPage").then((module) => ({
    default: module.EmotionPage,
  })),
);
import { MemoryPage } from "../features/memory/MemoryPage";
import { KnowledgePage } from "../features/knowledge/KnowledgePage";
import { RemindersPage } from "../features/reminders/RemindersPage";
import { ToolsPage } from "../features/tools/ToolsPage";
import { AuditPage } from "../features/audit/AuditPage";
export function createRouter() {
  return createBrowserRouter([
    {
      element: <AppShell />,
      errorElement: <div role="alert">页面加载失败，请刷新后重试。</div>,
      children: [
        { path: "/", element: <DashboardPage /> },
        { path: "/chat", element: <ChatPage /> },
        { path: "/persona", element: <PersonaPage /> },
        {
          path: "/emotion",
          element: (
            <Suspense fallback={<p role="status">正在加载情绪面板…</p>}>
              <EmotionPage />
            </Suspense>
          ),
        },
        { path: "/memory", element: <MemoryPage /> },
        { path: "/knowledge", element: <KnowledgePage /> },
        { path: "/reminders", element: <RemindersPage /> },
        { path: "/tools", element: <ToolsPage /> },
        { path: "/audit", element: <AuditPage /> },
      ],
    },
  ]);
}
