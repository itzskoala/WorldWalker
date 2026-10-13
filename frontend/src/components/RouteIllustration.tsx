// A custom, hand-drawn scene (not a stock photo or icon-library import)
// used on both the landing page hero and the two-column auth layout -
// one component so the two places share the exact same visual, not two
// near-duplicates. Same line-art language as icons.tsx (round joins,
// ~1.7-1.8 stroke) and the same "quiet dashed route, checkpoints pop
// when reached" convention TripDetailPage.tsx's real map already uses -
// a route with two muted, already-passed checkpoints, a walker at the
// current position, one emerald "active" checkpoint ahead, a postcard
// and a badge chip nearby standing in for the collection those
// checkpoints build toward.

interface RouteIllustrationProps {
  className?: string
}

export function RouteIllustration({ className }: RouteIllustrationProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 440 360"
      fill="none"
      role="img"
      aria-label="A dashed walking route across a map, with checkpoints, a walker, a postcard, and a badge"
    >
      <rect x="1" y="1" width="438" height="358" rx="22" fill="var(--field-bg)" stroke="var(--card-border)" />

      {/* The route itself - faint and dashed, same convention tripMap.ts
          uses for the unwalked portion of a real route. */}
      <path
        d="M56 272c34-10 54-40 46-70-9-32-48-38-54-8-6 28 30 40 58 24 42-24 46-86 100-100 46-12 70 20 96 4 22-14 18-46 48-54"
        stroke="var(--ink-faint)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray="2 10"
      />

      {/* Two already-passed checkpoints - small, hollow, muted. */}
      <circle cx="56" cy="272" r="7" fill="var(--card-bg)" stroke="var(--ink-faint)" strokeWidth="2.5" />
      <circle cx="146" cy="222" r="7" fill="var(--card-bg)" stroke="var(--ink-faint)" strokeWidth="2.5" />

      {/* The walker - simple stick figure mid-stride, at the current
          position along the route. */}
      <g transform="translate(206 150)" stroke="var(--ink)" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="0" cy="-30" r="6.5" fill="var(--ink)" stroke="none" />
        <path d="M0-21v16" />
        <path d="M0-16-11-8" />
        <path d="M0-16 10-10" />
        <path d="M0-5-10 14" />
        <path d="M0-5 9 15" />
      </g>

      {/* The active checkpoint ahead on the route - filled emerald pin,
          same "the nearest unreached one pops" idea as the real map. */}
      <g transform="translate(300 86)">
        <path
          d="M0 23S-15 8-15-2a15 15 0 1 1 30 0C15 8 0 23 0 23Z"
          fill="var(--green)"
          stroke="var(--green)"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <circle cx="0" cy="-2" r="5" fill="var(--card-bg)" />
      </g>

      {/* Postcard chip - a little rotated card with a simple photo glyph,
          standing in for the collection a finished walk builds. */}
      <g transform="translate(330 220) rotate(-8)">
        <rect x="-32" y="-22" width="64" height="44" rx="7" fill="var(--card-bg)" stroke="var(--card-border)" strokeWidth="1.5" />
        <rect x="-23" y="-13" width="46" height="26" rx="3" stroke="var(--blue)" strokeWidth="1.6" />
        <path d="m-23 7 11-11a3 3 0 0 1 4.2 0L4 8" stroke="var(--blue)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="-12" cy="-4" r="2.6" stroke="var(--blue)" strokeWidth="1.6" />
      </g>

      {/* Badge chip - a small medal, near the active checkpoint. */}
      <g transform="translate(356 128) rotate(10)">
        <circle r="18" fill="var(--card-bg)" stroke="var(--card-border)" strokeWidth="1.5" />
        <circle r="11" stroke="var(--green)" strokeWidth="2" />
        <path
          d="M0-6.5 1.8-2 6.7-1.6 3-1.6 4.1 2.8 0 0.2-4.1 2.8-3-1.6-6.7-1.6-1.8-2Z"
          fill="var(--green)"
        />
      </g>
    </svg>
  )
}
