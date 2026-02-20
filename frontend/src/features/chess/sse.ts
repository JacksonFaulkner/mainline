export type SseCallbacks = {
  onEvent: (eventName: string, eventData: string) => void
  onOpen?: () => void
  onClose?: () => void
  onError?: (error: Error) => void
}

export type SseStreamHandle = {
  close: () => void
}

function parseSseEventBlock(
  block: string,
): { eventName: string; eventData: string } | null {
  const lines = block.split("\n")
  let eventName = "message"
  const dataLines: string[] = []

  for (const line of lines) {
    if (!line || line.startsWith(":")) continue
    if (line.startsWith("event:")) {
      eventName = line.slice("event:".length).trim() || "message"
      continue
    }
    if (line.startsWith("data:")) {
      let value = line.slice("data:".length)
      if (value.startsWith(" ")) value = value.slice(1)
      dataLines.push(value)
    }
  }

  if (dataLines.length === 0) return null
  return { eventName, eventData: dataLines.join("\n") }
}

function emitBufferedEvents(
  buffer: string,
  onEvent: (eventName: string, eventData: string) => void,
): string {
  let working = buffer.replace(/\r\n/g, "\n")
  let delimiterIndex = working.indexOf("\n\n")

  while (delimiterIndex !== -1) {
    const rawBlock = working.slice(0, delimiterIndex)
    working = working.slice(delimiterIndex + 2)

    const parsed = parseSseEventBlock(rawBlock)
    if (parsed) onEvent(parsed.eventName, parsed.eventData)

    delimiterIndex = working.indexOf("\n\n")
  }

  return working
}

export function openAuthenticatedSse(
  url: string,
  token: string,
  callbacks: SseCallbacks,
): SseStreamHandle {
  const controller = new AbortController()
  let closed = false

  const close = () => {
    if (closed) return
    closed = true
    controller.abort()
    callbacks.onClose?.()
  }

  const run = async () => {
    try {
      const response = await fetch(url, {
        method: "GET",
        headers: {
          Accept: "text/event-stream",
          Authorization: `Bearer ${token}`,
        },
        cache: "no-store",
        signal: controller.signal,
      })

      if (!response.ok) {
        let reason = `${response.status} ${response.statusText}`
        try {
          const body = await response.text()
          if (body.trim()) reason = body
        } catch {
          // ignore body parse failures on error responses
        }
        throw new Error(`Stream request failed: ${reason}`)
      }

      if (!response.body) {
        throw new Error("Stream request returned no readable body.")
      }

      callbacks.onOpen?.()
      const decoder = new TextDecoder()
      const reader = response.body.getReader()
      let buffer = ""

      while (!closed) {
        const { done, value } = await reader.read()
        if (done) break
        if (!value) continue
        buffer += decoder.decode(value, { stream: true })
        buffer = emitBufferedEvents(buffer, callbacks.onEvent)
      }

      if (!closed) {
        closed = true
        callbacks.onClose?.()
      }
    } catch (error) {
      if (controller.signal.aborted) return
      const normalizedError =
        error instanceof Error ? error : new Error("Unknown stream error.")
      callbacks.onError?.(normalizedError)
    }
  }

  void run()

  return { close }
}
