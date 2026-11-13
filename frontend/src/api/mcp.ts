import client from './client'
import type { BrowserSetting, McpStatus } from '@/types/mcp'

export function getMcpStatus() {
  return client.get<McpStatus>('/mcp/status')
}

export function getBrowserSetting() {
  return client.get<BrowserSetting>('/mcp/browser-settings')
}

export function updateBrowserSetting(enabled: boolean) {
  return client.put<BrowserSetting>('/mcp/browser-settings', { cloakbrowser_enabled: enabled })
}
