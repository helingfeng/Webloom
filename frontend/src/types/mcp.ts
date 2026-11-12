export interface McpTool {
  name: string
  description: string
  input_schema: Record<string, unknown>
}

export interface McpStatus {
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
