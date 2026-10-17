export function createSSEParser(onEvent: (name: string, data: any) => void) {
  let buffer = ''
  return (text: string) => {
    buffer += text
    while (true) {
      const match = /\r?\n\r?\n/.exec(buffer)
      if (!match) return
      const frame = buffer.slice(0, match.index)
      buffer = buffer.slice(match.index + match[0].length)
      let name = 'message'
      let seq = 0
      const data: string[] = []
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith('event:')) name = line.slice(6).trim()
        if (line.startsWith('id:')) seq = Number(line.slice(3).trim()) || 0
        if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
      }
      if (data.length) onEvent(name, { ...JSON.parse(data.join('\n')), seq })
    }
  }
}
