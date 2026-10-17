"""Generic buffered streaming policy; business filters are injected."""
import re

class StreamingGuard:
    def __init__(self, sanitize, max_sentences: int = 3):
        self.sanitize = sanitize
        self.max_sentences = max_sentences
        self.pending = ''
        self.count = 0
        self.changed = False

    def _release(self, text):
        if self.count >= self.max_sentences:
            self.changed = True
            return ''
        safe = self.sanitize(text)
        self.changed |= safe != text
        parts = re.findall(r'[^。！？!?]+[。！？!?]?', safe)
        left = self.max_sentences - self.count
        if len(parts) > left: self.changed = True
        parts = parts[:left]
        self.count += len(parts)
        return ''.join(parts).strip()

    def feed(self, text):
        self.pending += text
        result = ''
        while True:
            match = re.search(r'[。！？!?]', self.pending)
            if not match: break
            sentence, self.pending = self.pending[:match.end()], self.pending[match.end():]
            result += self._release(sentence)
        return result

    def finish(self):
        result = self._release(self.pending) if self.pending.strip() else ''
        self.pending = ''
        return result
