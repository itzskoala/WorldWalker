import { useEffect, useRef, useState } from 'react'

const TYPE_MS = 38
const DELETE_MS = 22
const HOLD_MS = 1800
const PAUSE_MS = 400

interface TypewriterHeadlineProps {
  prefix: string
  variants: string[]
}

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function TypewriterHeadline({ prefix, variants }: TypewriterHeadlineProps) {
  const [text, setText] = useState(prefix + variants[0])
  const reduced = useRef(prefersReducedMotion())

  useEffect(() => {
    if (reduced.current) return

    let variantIndex = 0
    let timeoutId: number

    function nextVariantIndex(current: number): number {
      if (variants.length <= 1) return 0
      let next = current
      while (next === current) {
        next = Math.floor(Math.random() * variants.length)
      }
      return next
    }

    function type(full: string, pos: number) {
      setText(full.slice(0, pos))
      if (pos < full.length) {
        timeoutId = window.setTimeout(() => type(full, pos + 1), TYPE_MS)
      } else {
        timeoutId = window.setTimeout(() => erase(full), HOLD_MS)
      }
    }

    function erase(full: string) {
      if (full.length <= prefix.length) {
        variantIndex = nextVariantIndex(variantIndex)
        timeoutId = window.setTimeout(() => type(prefix + variants[variantIndex], prefix.length), PAUSE_MS)
        return
      }
      const next = full.slice(0, full.length - 1)
      setText(next)
      timeoutId = window.setTimeout(() => erase(next), DELETE_MS)
    }

    timeoutId = window.setTimeout(() => erase(prefix + variants[0]), HOLD_MS)

    return () => window.clearTimeout(timeoutId)
  }, [prefix, variants])

  return (
    <h1 className="landing-hero-title">
      <span aria-hidden="true">
        {text}
        <span className="landing-hero-cursor" />
      </span>
      <span className="sr-only">{prefix + variants[0]}</span>
    </h1>
  )
}
