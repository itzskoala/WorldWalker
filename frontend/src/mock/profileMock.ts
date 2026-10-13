// Static placeholder content for the Profile redesign - badges,
// favorite walks, and postcards have no backend yet (see ProfilePage.tsx),
// so this stands in for those three API calls. Swap each array for a real
// fetch once that logic exists; the components below only care about the
// shapes defined here.

export type BadgeCategory = 'milestone' | 'nature' | 'city' | 'coastal'

export interface Badge {
  id: string
  name: string
  category: BadgeCategory
}

export interface FavoriteWalk {
  id: string
  name: string
  place: string
  distanceMiles: number
  durationLabel: string
  photoSeed: string
}

export interface Postcard {
  id: string
  place: string
  region: string
  photoSeed: string
}

export const EARNED_BADGES: Badge[] = [
  { id: 'first-steps', name: 'First Steps', category: 'milestone' },
  { id: 'nature-lover', name: 'Nature Lover', category: 'nature' },
  { id: 'city-explorer', name: 'City Explorer', category: 'city' },
  { id: 'coastal-walker', name: 'Coastal Walker', category: 'coastal' },
]

// Total badges this traveler has unlocked - more than are shown in the
// compact grid above, which is what the "+N more" tile counts up to.
export const TOTAL_BADGES_EARNED = 9

export const FAVORITE_WALKS: FavoriteWalk[] = [
  { id: 'cinque-terre', name: 'Cinque Terre Coastal Path', place: 'Cinque Terre, Italy', distanceMiles: 8.7, durationLabel: '3h 15m', photoSeed: 'cinque-terre' },
  { id: 'lake-tahoe', name: 'Lakeshore Loop', place: 'Lake Tahoe, USA', distanceMiles: 6.4, durationLabel: '2h 05m', photoSeed: 'lake-tahoe' },
  { id: 'central-park', name: 'Central Park Loop', place: 'New York, USA', distanceMiles: 4.4, durationLabel: '1h 20m', photoSeed: 'central-park' },
]

// The full library - the Postcards screen (PostcardsPage.tsx) shows all
// of these; the Profile screen's PostcardsLibrary card shows only
// PROFILE_POSTCARD_PREVIEW_COUNT of them, with "View all" linking to the
// full Postcards screen for the rest.
export const POSTCARDS: Postcard[] = [
  { id: 'cinque-terre', place: 'Cinque Terre', region: 'Italy', photoSeed: 'cinque-terre' },
  { id: 'lake-tahoe', place: 'Lake Tahoe', region: 'USA', photoSeed: 'lake-tahoe' },
  { id: 'central-park', place: 'Central Park', region: 'New York', photoSeed: 'central-park' },
  { id: 'santorini', place: 'Santorini', region: 'Greece', photoSeed: 'santorini' },
  { id: 'kyoto', place: 'Kyoto', region: 'Japan', photoSeed: 'kyoto' },
  { id: 'bali', place: 'Bali', region: 'Indonesia', photoSeed: 'bali' },
  { id: 'banff', place: 'Banff', region: 'Canada', photoSeed: 'banff' },
  { id: 'dolomites', place: 'The Dolomites', region: 'Italy', photoSeed: 'dolomites' },
  { id: 'kyoto-river', place: 'Kamo River', region: 'Kyoto, Japan', photoSeed: 'kamo-river' },
]

export const PROFILE_POSTCARD_PREVIEW_COUNT = 6

export function photoUrl(seed: string, width: number, height: number): string {
  return `https://picsum.photos/seed/${seed}/${width}/${height}`
}
