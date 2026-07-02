import Sidebar from "@/components/layout/Sidebar";
import ChatWindow from "@/components/chat/ChatWindow";

export default function ChatPage() {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 ml-14 flex flex-col min-h-0">
        {/* Header */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-rim flex-shrink-0">
          <div>
            <h1 className="text-text-primary font-semibold text-sm tracking-wide">DAWN</h1>
            <p className="text-text-muted text-xs">Knowledge Layer · Regent</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-dawn animate-pulse-slow" />
            <span className="text-text-muted text-xs font-mono">online</span>
          </div>
        </header>

        {/* Dawn line */}
        <div className="dawn-line flex-shrink-0" />

        {/* Chat fills remaining height */}
        <div className="flex-1 min-h-0">
          <ChatWindow />
        </div>
      </main>
    </div>
  );
}
