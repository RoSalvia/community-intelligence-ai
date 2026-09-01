import type { AnalysisResponse, AppClient, EvidenceResponse } from "./types"

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  const response = await fetch(input, init)
  if (!response.ok) {
    let message = `Request failed (${response.status}).`
    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) message = payload.detail
    } catch {
      // Keep the stable status-based fallback when a response is not JSON.
    }
    throw new Error(message)
  }
  return (await response.json()) as T
}

export const apiClient: AppClient = {
  runDemo: () =>
    requestJson<AnalysisResponse>("/api/analyses/demo", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ seed: 20260901, message_count: 120 }),
    }),

  importTelegram: (file, language = "und") => {
    const form = new FormData()
    form.append("file", file)
    form.append("language", language)
    return requestJson<AnalysisResponse>("/api/analyses/telegram", {
      method: "POST",
      body: form,
    })
  },

  getEvidence: (analysisId) =>
    requestJson<EvidenceResponse>(`/api/analyses/${analysisId}/evidence`),
}
