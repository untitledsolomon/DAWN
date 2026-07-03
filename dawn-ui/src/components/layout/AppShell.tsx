"use client";

import { useState, useCallback } from "react";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";

interface Props {
  children: React.ReactNode;
}

export default function AppShell({ children }: Props) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => !prev);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggle={toggleSidebar}
      />

      {/* Main content area */}
      <main className="flex-1 flex flex-col min-w-0">
        <TopBar onToggleSidebar={toggleSidebar} />
        <div className="flex-1 min-h-0 overflow-hidden">
          {children}
        </div>
      </main>
    </div>
  );
}
