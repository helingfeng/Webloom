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

export interface AgentSkillSummary {
  name: string
  description: string
}

export interface AgentSkillDetail extends AgentSkillSummary {
  content: string
}

export interface SkillInstallClient {
  client: string
  user_dir: string
  project_dir: string
  command: string
}

export interface SkillInstallInfo {
  source_dir: string
  clients: SkillInstallClient[]
}
