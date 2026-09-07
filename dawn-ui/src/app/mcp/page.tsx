"use client";

import { useState, useEffect, useCallback } from "react";
import AppShell from "@/components/layout/AppShell";
import {
  listMCPServers,
  createMCPServer,
  deleteMCPServer,
  connectMCPServer,
  listMCPTools,
} from "@/lib/api";
import type { MCPServer, MCPTool } from "@/lib/api";
import {
  Server,
  Plus,
  Plug,
  Trash2,
  Loader2,
  Check,
  X,
  AlertCircle,
  Wrench,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import clsx from "clsx";

function MCPServersContent() {
  const [servers, setServers] = useState<MCPServer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add form state
  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formType, setFormType] = useState<"stdio" | "http">("stdio");
  const [formCommand, setFormCommand] = useState("");
  const [formArgs, setFormArgs] = useState("");
  const [formUrl, setFormUrl] = useState("");
  const [formApiKey, setFormApiKey] = useState("");
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Per-server action state
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [connectError, setConnectError] = useState<string | null>(null);

  // Tools browsing
  const [selectedServerId, setSelectedServerId] = useState<string | null>(null);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [toolsLoading, setToolsLoading] = useState(false);
  const [toolsError, setToolsError] = useState<string | null>(null);

  const fetchServers = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listMCPServers();
      setServers(data);
      setError(null);
    } catch (err) {
      console.error("[MCP] Failed to load servers:", err);
      setError("Failed to load MCP servers");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchServers();
  }, [fetchServers]);

  const loadTools = useCallback(async (serverId: string) => {
    try {
      setToolsLoading(true);
      setToolsError(null);
      const data = await listMCPTools(serverId);
      setTools(data);
    } catch (err) {
      console.error("[MCP] Failed to load tools:", err);
      setToolsError("Failed to load tools");
    } finally {
      setToolsLoading(false);
    }
  }, []);

  const handleSelectServer = async (server: MCPServer) => {
    if (selectedServerId === server.id) {
      setSelectedServerId(null);
      setTools([]);
      return;
    }
    setSelectedServerId(server.id);
    await loadTools(server.id);
  };

  const handleConnect = async (server: MCPServer) => {
    try {
      setConnectingId(server.id);
      setConnectError(null);
      await connectMCPServer(server.id);
      await fetchServers();
      // Refresh tools for the connected server if it's the selected one
      if (selectedServerId === server.id) {
        await loadTools(server.id);
      }
    } catch (err) {
      console.error("[MCP] Failed to connect:", err);
      setConnectError(err instanceof Error ? err.message : "Failed to connect");
    } finally {
      setConnectingId(null);
    }
  };

  const handleDelete = async (server: MCPServer) => {
    try {
      await deleteMCPServer(server.id);
      setServers((prev) => prev.filter((s) => s.id !== server.id));
      if (selectedServerId === server.id) {
        setSelectedServerId(null);
        setTools([]);
      }
    } catch (err) {
      console.error("[MCP] Failed to delete:", err);
      setConnectError(err instanceof Error ? err.message : "Failed to delete");
    }
  };

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setFormSubmitting(true);
      setFormError(null);
      await createMCPServer({
        name: formName.trim(),
        description: formDescription.trim() || undefined,
        server_type: formType,
        command: formType === "stdio" ? formCommand.trim() || undefined : undefined,
        args: formType === "stdio" ? formArgs.split(",").map((a) => a.trim()).filter(Boolean) : undefined,
        url: formType === "http" ? formUrl.trim() || undefined : undefined,
        api_key: formType === "http" ? formApiKey.trim() || undefined : undefined,
      });
      await fetchServers();
      // Reset form
      setShowForm(false);
      setFormName("");
      setFormDescription("");
      setFormCommand("");
      setFormArgs("");
      setFormUrl("");
      setFormApiKey("");
    } catch (err) {
      console.error("[MCP] Failed to create:", err);
      setFormError(err instanceof Error ? err.message : "Failed to create server");
    } finally {
      setFormSubmitting(false);
    }
  };

  const inputClass =
    "w-full bg-elevated/60 border border-rim rounded-lg px-3 py-1.5 text-xs text-text-primary placeholder:text-text-muted outline-none focus:border-dawn/40 transition-all";

  return (
    <div className="flex h-full">
      {/* Main column */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex-shrink-0 border-b border-rim px-4 sm:px-6 py-3">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h1 className="text-text-primary text-sm font-semibold">MCP Servers</h1>
              <p className="text-text-muted text-2xs mt-0.5">
                Model Context Protocol servers and their tools
              </p>
            </div>
            <button
              onClick={() => setShowForm((v) => !v)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/10 text-dawn text-xs hover:bg-dawn/20 transition-all"
            >
              <Plus size={12} />
              {showForm ? "Close" : "Add Server"}
            </button>
          </div>

          {/* Add form */}
          {showForm && (
            <form
              onSubmit={handleAdd}
              className="mb-2 p-3 rounded-xl bg-surface border border-rim space-y-3"
            >
              <div className="flex items-center justify-between">
                <h3 className="text-text-primary text-xs font-medium">New MCP Server</h3>
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="w-6 h-6 flex items-center justify-center rounded text-text-muted hover:text-text-secondary"
                >
                  <X size={12} />
                </button>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-1 block">
                    Name
                  </label>
                  <input
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="e.g. Filesystem"
                    required
                    className={inputClass}
                  />
                </div>
                <div>
                  <label className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-1 block">
                    Type
                  </label>
                  <select

                    value={formType}
                    onChange={(e) => setFormType(e.target.value as "stdio" | "http")}
                    className={inputClass}
                  >
                    <option value="stdio">stdio</option>
                    <option value="http">http</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-1 block">
                  Description
                </label>
                <input
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  placeholder="Optional description"
                  className={inputClass}
                />
              </div>

              {formType === "stdio" ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-1 block">
                      Command
                    </label>
                    <input
                      value={formCommand}
                      onChange={(e) => setFormCommand(e.target.value)}
                      placeholder="e.g. npx"
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-1 block">
                      Args (comma-separated)
                    </label>
                    <input
                      value={formArgs}
                      onChange={(e) => setFormArgs(e.target.value)}
                      placeholder="e.g. -y, @modelcontextprotocol/server-filesystem"
                      className={inputClass}
                    />
                  </div>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-1 block">
                      URL
                    </label>
                    <input
                      value={formUrl}
                      onChange={(e) => setFormUrl(e.target.value)}
                      placeholder="https://..."
                      className={inputClass}
                    />
                  </div>
                  <div>
                    <label className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-1 block">
                      API Key (optional)
                    </label>
                    <input
                      value={formApiKey}
                      onChange={(e) => setFormApiKey(e.target.value)}
                      placeholder="Optional API key"
                      type="password"
                      className={inputClass}
                    />
                  </div>
                </div>
              )}

              {formError && (
                <div className="flex items-center gap-1 text-ember text-2xs">
                  <AlertCircle size={11} />
                  {formError}
                </div>
              )}

              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={formSubmitting}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-dawn/10 text-dawn text-xs hover:bg-dawn/20 transition-all disabled:opacity-50"
                >
                  {formSubmitting ? <Loader2 size={11} className="animate-spin" /> : <Plus size={11} />}
                  Add
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 size={20} className="text-dawn animate-spin" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full gap-2">
              <AlertCircle size={18} className="text-ember" />
              <p className="text-text-muted text-sm">{error}</p>
              <button
                onClick={fetchServers}
                className="px-3 py-1.5 rounded-lg bg-dawn/10 text-dawn text-xs hover:bg-dawn/20 transition-all"
              >
                Retry
              </button>
            </div>
          ) : servers.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-2">
              <Server size={24} className="text-text-muted/50" />
              <p className="text-text-muted text-sm">No MCP servers configured yet. Add one to get started.</p>
            </div>
          ) : (
            <div className="space-y-3">
              {servers.map((server) => {
                const isSelected = selectedServerId === server.id;
                const isConnecting = connectingId === server.id;
                return (
                  <div
                    key={server.id}
                    className="rounded-xl bg-surface border border-rim overflow-hidden"
                  >
                    {/* Card header */}
                    <div className="p-3 flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3 min-w-0">
                        <div
                          className={clsx(
                            "w-8 h-8 rounded-lg flex items-center justify-center border flex-shrink-0",
                            server.enabled
                              ? "text-dawn bg-dawn/10 border-dawn/20"
                              : "text-text-muted bg-elevated/60 border-rim"
                          )}
                        >
                          <Server size={14} />
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <h3 className="text-text-primary text-xs font-medium truncate">{server.name}</h3>
                            <span className="px-1.5 py-0.5 rounded bg-elevated/60 border border-rim text-text-muted text-2xs uppercase">
                              {server.server_type}
                            </span>
                          </div>
                          {server.description && (
                            <p className="text-text-muted text-2xs mt-0.5 line-clamp-2">{server.description}</p>
                          )}
                          <div className="flex items-center gap-3 mt-1.5">
                            <span
                              className={clsx(
                                "flex items-center gap-1 text-2xs",
                                server.enabled ? "text-emerald-400" : "text-text-muted"
                              )}
                            >
                              <span
                                className={clsx(
                                  "w-1.5 h-1.5 rounded-full",
                                  server.enabled ? "bg-emerald-400" : "bg-text-muted"
                                )}
                              />
                              {server.enabled ? "Connected" : "Not connected"}
                            </span>
                            <span className="flex items-center gap-1 text-text-muted text-2xs">
                              <Wrench size={9} />
                              {server.tools_count} tools
                            </span>
                            {server.last_connected_at && (
                              <span className="text-text-muted text-2xs">
                                Last connected {new Date(server.last_connected_at).toLocaleString()}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-1 flex-shrink-0">
                        <button
                          onClick={() => handleConnect(server)}
                          disabled={isConnecting}
                          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-dawn/10 text-dawn text-xs hover:bg-dawn/20 transition-all disabled:opacity-50"
                          title="Connect and discover tools"
                        >
                          {isConnecting ? (
                            <Loader2 size={11} className="animate-spin" />
                          ) : (
                            <Plug size={11} />
                          )}
                          Connect
                        </button>
                        <button
                          onClick={() => handleDelete(server)}
                          className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-ember hover:border-ember/30 border border-transparent transition-all"
                          title="Delete"
                        >
                          <Trash2 size={11} />
                        </button>
                        <button
                          onClick={() => handleSelectServer(server)}
                          className="w-7 h-7 flex items-center justify-center rounded text-text-muted hover:text-text-secondary transition-all"
                          title={isSelected ? "Hide tools" : "Browse tools"}
                        >
                          {isSelected ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                        </button>
                      </div>
                    </div>

                    {/* Tools section */}
                    {isSelected && (
                      <div className="border-t border-rim p-3 bg-abyss/40">
                        <h4 className="text-text-muted text-2xs font-medium uppercase tracking-wider mb-2">
                          Tools
                        </h4>
                        {toolsLoading ? (
                          <div className="flex items-center gap-2 text-text-muted text-2xs py-2">
                            <Loader2 size={12} className="animate-spin text-dawn" />
                            Loading tools...
                          </div>
                        ) : toolsError ? (
                          <div className="flex items-center gap-2 text-ember text-2xs py-2">
                            <AlertCircle size={11} />
                            {toolsError}
                          </div>
                        ) : tools.length === 0 ? (
                          <p className="text-text-muted text-2xs py-2">
                            No tools discovered. Click "Connect" to discover tools for this server.
                          </p>
                        ) : (
                          <div className="flex flex-wrap gap-2">
                            {tools.map((tool) => (
                              <div
                                key={tool.id}
                                className="px-2.5 py-1.5 rounded-lg bg-surface border border-rim max-w-xs"
                              >
                                <div className="flex items-center gap-1.5">
                                  <Wrench size={10} className="text-dawn flex-shrink-0" />
                                  <span className="text-text-primary text-2xs font-medium truncate">
                                    {tool.name}
                                  </span>
                                  {tool.enabled && <Check size={9} className="text-emerald-400 flex-shrink-0" />}
                                </div>
                                {tool.description && (
                                  <p className="text-text-muted text-2xs mt-0.5 line-clamp-2">
                                    {tool.description}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function MCPServersPage() {
  return (
    <AppShell>
      <MCPServersContent />
    </AppShell>
  );
}
