import client from './client'
import type { McpStatus } from '@/types/mcp'

export function getMcpStatus() {
  return client.get<McpStatus>('/mcp/status')
}
