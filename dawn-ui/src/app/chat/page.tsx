"use client";

import { Suspense } from "react";
import AppShell from "@/components/layout/AppShell";
import ChatWindow from "@/components/chat/ChatWindow";

function ChatContent() {
  return <ChatWindow />;
}

export default function ChatPage() {
  return (
    <AppShell>
      <Suspense fallback={
        <div className="flex items-center justify-center h-full">
          <div className="text-text-muted text-sm">Loading chat...</div>
        </div>
      }>
        <ChatContent />
      </Suspense>
    </AppShell>
  );
}
