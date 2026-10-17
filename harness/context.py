"""Bounded context preserving message groups with exact excerpt summaries."""
def compact_history(messages: list[dict], max_chars: int = 12000) -> tuple[list[dict], str]:
    groups: list[list[dict]] = []
    for item in messages:
        if item['role'] == 'system': continue
        if item['role'] == 'user' or not groups: groups.append([])
        groups[-1].append(item)
    retained, used, removed = [], 0, []
    for group in reversed(groups):
        size = sum(len(str(m.get('content') or '')) for m in group)
        if retained and used + size > max_chars: removed = group + removed
        else: retained = group + retained; used += size
    # This is a transparent excerpt, never labelled as a semantic model summary.
    summary = '\n'.join(f"{m['role']}: {str(m.get('content', ''))[:160]}" for m in removed if m['role'] in {'user', 'assistant'})[-2000:]
    return retained, summary
