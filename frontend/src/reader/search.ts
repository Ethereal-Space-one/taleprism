import { Converter } from 'opencc-js/t2cn'
import { literalMatches, type TextMatcher, type TextMatch } from './model'

// Generic t2s only: no regional vocabulary, Japanese conversion, case folding,
// punctuation/whitespace removal, Unicode compatibility normalization outside Han,
// fuzzy search, or changes to the rendered source. This module loads on search.
const toSimplified = Converter({ from: 't', to: 'cn' })
type Folded = { text: string; source: (number | undefined)[] }
function fold(text: string): Folded {
  let folded = '',
    offset = 0
  const source: (number | undefined)[] = [0]
  for (const part of text.matchAll(/\p{Script=Han}+|[^\p{Script=Han}]+/gu)) {
    const original = [...part[0]]
    let converted = /^\p{Script=Han}/u.test(part[0]) ? [...toSimplified(part[0])] : original
    // The pinned t2s dictionaries preserve scalar count (covered by an exhaustive
    // dependency test). Never guess offsets if a future mapping expands/contracts.
    if (converted.length !== original.length) converted = original
    for (let i = 0; i < original.length; i++) {
      folded += converted[i]
      offset += original[i].length
      source[folded.length] = offset
    }
  }
  return { text: folded, source }
}

export function createSearchMatcher(): TextMatcher {
  // Reader-local bounded cache, not a persistent copy of private source/searches.
  const cache = new Map<string, Folded>()
  const cached = (text: string) => {
    const hit = cache.get(text)
    if (hit) return hit
    const value = fold(text)
    if (cache.size === 256) cache.delete(cache.keys().next().value!)
    cache.set(text, value)
    return value
  }
  return (text, query) => {
    if (!query) return []
    const source = cached(text),
      needle = cached(query).text
    const matches = new Map<string, TextMatch>()
    // Keep literal matches even when a partial query folds differently in context
    // (e.g. 乾 alone versus 乾坤). Ambiguous forms like 發/髮 share simplified 发;
    // exact mode bypasses this matcher entirely.
    for (const range of literalMatches(text, query))
      matches.set(`${range.start}:${range.end}`, range)
    for (const range of literalMatches(source.text, needle)) {
      const start = source.source[range.start],
        end = source.source[range.end]
      if (start !== undefined && end !== undefined) matches.set(`${start}:${end}`, { start, end })
    }
    const ordered = [...matches.values()].sort((a, b) => a.start - b.start || a.end - b.end)
    let end = 0
    return ordered.filter((match) => {
      if (match.start < end) return false
      end = match.end
      return true
    })
  }
}
