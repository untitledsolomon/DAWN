"use client";

import { useState, useCallback, useEffect } from "react";
import Sidebar from "./Sidebar";
import TopBar from "./TopBar";
import { Menu, X } from "lucide-react";
import clsx from "clsx";

interface Props {
  children: React.ReactNode;
}

export default function AppShell({ children }: Props) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((prev) => !prev);
  }, []);

  const toggleMobileSidebar = useCallback(() => {
    setMobileSidebarOpen((prev) => !prev);
  }, []);

  // Close mobile sidebar on route change (handled via resize/click outside)
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 768) {
        setMobileSidebarOpen(false);
      }
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  return (
    <div className="flex h-dvh overflow-hidden bg-abyss">
      {/* Mobile sidebar overlay */}
      {mobileSidebarOpen && (
        <div
          className="fixed inset-0 bg-black/30 z-40 md:hidden"
          onClick={() => setMobileSidebarOpen(false)}
        />
      )}

      {/* Sidebar — hidden on mobile unless toggled */}
      <div
        className={clsx(
          "fixed md:relative z-50 h-full transition-transform duration-200",
          "md:block",
          mobileSidebarOpen
            ? "translate-x-0"
            : "-translate-x-full md:translate-x-0",
        )}
      >
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggle={toggleSidebar}
          onMobileClose={() => setMobileSidebarOpen(false)}
        />
      </div>

      {/* Main content area */}
      <main className="flex-1 flex flex-col min-w-0 max-w-full">
        <TopBar
          onToggleSidebar={toggleSidebar}
          onToggleMobileSidebar={toggleMobileSidebar}
          mobileSidebarOpen={mobileSidebarOpen}
        />
        <div className="flex-1 min-h-0 overflow-hidden">
          {children}
        </div>
      </main>
    </div>
  );
}
