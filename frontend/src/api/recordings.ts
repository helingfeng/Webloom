import client from './client'
import type { RecordingSession } from '@/types/recording'

export function startRecording(startUrl: string) {
  return client.post<RecordingSession>('/recordings/start', { start_url: startUrl })
}

export function getRecording(id: number) {
  return client.get<RecordingSession>(`/recordings/${id}`)
}

export function stopRecording(id: number) {
  return client.post<RecordingSession>(`/recordings/${id}/stop`)
}
