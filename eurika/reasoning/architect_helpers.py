"""Architect formatting helpers (extracted for file size)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from eurika.knowledge import KnowledgeProvider
    from eurika.storage.events import Event

SMELL_HOW_MAP: Dict[str, str] = {
    'god_module': 'Split into focused modules by responsibility (e.g. core, analysis, reporting, CLI).',
    'bottleneck': 'Introduce a facade so dependents use a stable interface instead of the concrete implementation.',
    'hub': 'Decompose and split responsibilities; extract sub-modules.',
    'cyclic_dependency': 'Break the cycle via dependency inversion or an abstraction layer that both sides depend on.',
}
SMELL_REF_SUFFIX: str = ' See Reference block for documentation.'


def format_recent_events(events: List['Event'], max_chars: int = 500) -> str:
    """Format recent patch/learn events for architect prompt (ROADMAP 3.2.3, Review III)."""
    if not events:
        return ''
    lines: List[str] = []
    for e in events[:10]:
        if e.type == 'patch':
            modified = e.output.get('modified', [])
            res = e.result
            fail = e.output.get('failure_reason')
            extra = f', failure={fail}' if (res is False and fail) else ''
            lines.append(f'patch: modified {len(modified)} file(s), verify={res}{extra}')
        elif e.type == 'learn':
            modules = e.input.get('modules', [])
            res = e.result
            fail = e.output.get('failure_reason')
            mods = ', '.join(modules[:3]) + ('...' if len(modules) > 3 else '')
            extra = f', failure={fail}' if (res is False and fail) else ''
            lines.append(f'learn: modules [{mods}], success={res}{extra}')
        else:
            lines.append(f'{e.type}: result={e.result}')
    out = '; '.join(lines)
    return out[:max_chars] + ('...' if len(out) > max_chars else '')


def format_knowledge_fragments(fragments: List[Dict[str, Any]]) -> str:
    """Format knowledge fragments for inclusion in prompt or template."""
    if not fragments:
        return ''
    lines: List[str] = []
    for i, f in enumerate(fragments[:10], 1):
        if not isinstance(f, dict):
            continue
        title = f.get('title') or f.get('name') or f'Fragment {i}'
        content = f.get('content') or f.get('text') or str(f)
        lines.append(f'- {title}: {content[:500]}' + ('...' if len(str(content)) > 500 else ''))
    return '\n'.join(lines) if lines else ''


def summarize_patch_plan(patch_plan: Optional[Dict[str, Any]]) -> tuple[int, Dict[str, int], List[str]]:
    """Extract count/kind breakdown/targets from patch plan."""
    if not (patch_plan and patch_plan.get('operations')):
        return (0, {}, [])
    ops = patch_plan['operations']
    kind_counts: Dict[str, int] = {}
    for o in ops:
        k = o.get('kind', 'refactor')
        kind_counts[k] = kind_counts.get(k, 0) + 1
    targets = list({o.get('target_file', '') for o in ops if o.get('target_file')})[:5]
    return (len(ops), kind_counts, targets)


def format_template_patch_plan_sentence(patch_plan: Optional[Dict[str, Any]]) -> str:
    """Template sentence describing planned refactorings."""
    total, kind_counts, targets = summarize_patch_plan(patch_plan)
    if not (total and targets):
        return ''
    kinds = ', '.join((f'{k}={v}' for k, v in sorted(kind_counts.items())))
    return f"Planned refactorings: {total} ops ({kinds}); top targets: {', '.join(targets[:3])}."


def build_llm_patch_desc(patch_plan: Optional[Dict[str, Any]]) -> str:
    """Prompt block with patch-plan context for LLM."""
    total, _kind_counts, targets = summarize_patch_plan(patch_plan)
    if total == 0:
        return ''
    ops = patch_plan.get('operations', []) if isinstance(patch_plan, dict) else []
    kinds = [o.get('kind', 'refactor') for o in ops if isinstance(o, dict)]
    return f'\n\nPlanned patch operations: {total} total. Kinds: {kinds[:10]}. Top target modules: {targets[:5]}. Consider these in your recommendation.'


def resolve_knowledge_snippet(
    knowledge_provider: Optional['KnowledgeProvider'],
    knowledge_topic: Optional[Union[str, List[str]]],
) -> str:
    """Resolve and format knowledge snippets from provider/topics."""
    if not (knowledge_provider and knowledge_topic):
        return ''
    from eurika.knowledge import StructuredKnowledge
    topics = [knowledge_topic] if isinstance(knowledge_topic, str) else knowledge_topic
    all_fragments: List[Dict[str, Any]] = []
    for t in topics:
        if not t:
            continue
        kn = knowledge_provider.query(t.strip())
        if isinstance(kn, StructuredKnowledge) and (not kn.is_empty()):
            all_fragments.extend(kn.fragments)
    return format_knowledge_fragments(all_fragments) if all_fragments else ''


def template_structure_sentence(modules: int, deps: int, cycles: int) -> str:
    """Sentence describing structural graph size and cyclicity."""
    if cycles == 0:
        return f'The codebase has {modules} modules and {deps} dependencies with no cycles.'
    return f'The codebase has {modules} modules, {deps} dependencies and {cycles} cycles.'


def parse_smell_from_risk(risk: str) -> Optional[str]:
    """Extract smell type from risk string (e.g. 'god_module @ patch_engine.py' -> 'god_module')."""
    if not risk or not isinstance(risk, str):
        return None
    parts = risk.strip().split()
    if not parts:
        return None
    first = parts[0].lower()
    return first if first in SMELL_HOW_MAP else None


def build_recommendation_how_block(risks: List[str], knowledge_snippet: str) -> str:
    """Build concrete 'how to fix' block for top risks (ROADMAP 2.9.1)."""
    seen: set[str] = set()
    lines: List[str] = []
    for r in (risks or [])[:5]:
        smell = parse_smell_from_risk(r)
        if not smell or smell in seen:
            continue
        seen.add(smell)
        how = SMELL_HOW_MAP.get(smell)
        if how:
            lines.append(f'- {smell}: {how}')
    if not lines:
        return ''
    ref_note = SMELL_REF_SUFFIX if knowledge_snippet else ''
    return '\n\nRecommendation (how to fix):\n' + '\n'.join(lines) + ref_note


def template_risks_sentence(risks: List[str], central_modules: List[Dict[str, Any]]) -> str:
    """Sentence about top risks; fallback to central modules when risks absent."""
    if risks:
        top = risks[:3]
        risk_str = '; '.join(top) if len(top) <= 2 else top[0] + ' and ' + str(len(risks) - 1) + ' more'
        return f'Main risks: {risk_str}.'
    if central_modules:
        names = [c.get('name', '') for c in central_modules[:3] if isinstance(c, dict)]
        return f"Central modules: {', '.join(names)}."
    return ''


def template_trends_sentences(trend_complexity: str, trend_smells: str, regressions: List[str]) -> List[str]:
    """Optional trend and regression sentences."""
    out: List[str] = []
    if trend_complexity != 'unknown' or trend_smells != 'unknown':
        out.append(f'Trends: complexity {trend_complexity}, smells {trend_smells}.')
    if regressions:
        out.append(f"Potential regressions: {'; '.join(regressions[:2])}.")
    return out


def template_context_sentences(
    patch_plan: Optional[Dict[str, Any]],
    knowledge_snippet: str,
    recent_events_snippet: str,
) -> List[str]:
    """Optional sentences for patch-plan and recent events. Reference shown in dedicated block (2.9.1)."""
    out: List[str] = []
    patch_sentence = format_template_patch_plan_sentence(patch_plan)
    if patch_sentence:
        out.append(patch_sentence)
    if recent_events_snippet:
        out.append(f'Recent actions: {recent_events_snippet}.')
    return out


def format_reference_block(knowledge_snippet: str, max_chars: int = 800) -> str:
    """Format Knowledge snippets as a dedicated Reference block (ROADMAP 2.9.1)."""
    if not knowledge_snippet or not knowledge_snippet.strip():
        return ''
    snip = knowledge_snippet.strip()
    if len(snip) > max_chars:
        snip = snip[:max_chars] + '...'
    return '\n\nReference (from documentation):\n' + snip
