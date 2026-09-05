export interface RecordingSession {
  recording_id: number
  status: 'recording' | 'completed' | 'failed'
  start_url: string
  raw_code: string
  code: string
  detected_start_url: string
  error: string
  applied_globals: {
    headers: Record<string, string>
    vars: Record<string, string>
    localStorage: Record<string, string>
    cookies: { name: string; value: string; domain: string; path: string }[]
  }
}
