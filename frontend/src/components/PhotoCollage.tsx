// The landing hero's photo collage - four real walking/travel photos
// scattered and overlapping like a scrapbook (not a grid), replacing
// JourneyCard.tsx's animated illustration entirely per the simplified
// hero redesign. Pure CSS positioning (position: absolute tiles in one
// position: relative wrapper) - the only way to get tiles that overlap
// and vary in size without fighting a grid.
//
// Each photo is real content (what someone using WorldWalker is actually
// doing - running, hiking, way-finding, climbing stairs), not pure
// decoration standing in for something else, so the wrapper is NOT
// aria-hidden and every <img> keeps real alt text - a screen reader
// should be able to tell what this hero is showing the same way a
// sighted visitor can.

interface Tile {
  src: string
  alt: string
  width: number
  height: number
  className: string
  priority?: boolean
}

const TILES: Tile[] = [
  {
    src: '/hero/runners.webp',
    alt: 'Three women running along a waterfront path at sunrise, ocean in the background',
    width: 640,
    height: 960,
    className: 'collage-tile collage-tile-main',
    priority: true,
  },
  {
    src: '/hero/hiker-ridge.webp',
    alt: "A hiker's silhouette walking along a rocky mountain ridge at dusk, misty peaks in the distance",
    width: 640,
    height: 427,
    className: 'collage-tile collage-tile-hiker',
  },
  {
    src: '/hero/signpost.webp',
    alt: 'A signpost covered in stickers, with arrows pointing toward cities around the world including New York, London, and Sydney',
    width: 640,
    height: 960,
    className: 'collage-tile collage-tile-signpost',
  },
  {
    src: '/hero/stairs.webp',
    alt: 'Close-up of a person in orange running shoes walking up a stone staircase',
    width: 640,
    height: 427,
    className: 'collage-tile collage-tile-stairs',
  },
]

export function PhotoCollage({ className }: { className?: string }) {
  return (
    <div className={`photo-collage ${className ?? ''}`.trim()}>
      {TILES.map((tile) => (
        <img
          key={tile.src}
          src={tile.src}
          alt={tile.alt}
          width={tile.width}
          height={tile.height}
          className={tile.className}
          loading={tile.priority ? 'eager' : 'lazy'}
          fetchPriority={tile.priority ? 'high' : 'auto'}
        />
      ))}
    </div>
  )
}
