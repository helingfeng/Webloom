import client from './client'
import type {
  AgentSkillDetail,
  AgentSkillSummary,
  McpStatus,
  SkillInstallInfo,
} from '@/types/mcp'

export function getMcpStatus() {
  return client.get<McpStatus>('/mcp/status')
}

export function listAgentSkills() {
  return client.get<AgentSkillSummary[]>('/mcp/skills')
}

export function getSkillsInstallInfo() {
  return client.get<SkillInstallInfo>('/mcp/skills/install')
}

export function getAgentSkill(name: string) {
  return client.get<AgentSkillDetail>(`/mcp/skills/${name}`)
}
