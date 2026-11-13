export interface McpTool {
  name: string
  description: string
  input_schema: Record<string, unknown>
}

export interface BrowserSetting {
  engine: 'playwright' | 'cloakbrowser'
  cloakbrowser_enabled: boolean
  ready: boolean
  cloakbrowser_installed: boolean
  license_configured: boolean
  humanize: boolean
  proxy_configured: boolean
  message: string
}

export interface McpStatus {
  collection_policy?: {
    min_interval_seconds: number
    cooldown_seconds: number
    max_requests: number
    max_wait_seconds: number
  }
  browser?: Omit<BrowserSetting, 'cloakbrowser_enabled'>
  server_name: string
  transport: string
  endpoint: { direct: string; proxied: string }
  tool_count: number
  tools: McpTool[]
  client_config: {
    mcp_servers_json: Record<string, unknown>
    claude_cli_command: string
    trae_cli_command: string
  }
}
