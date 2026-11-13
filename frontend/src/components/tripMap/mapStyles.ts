// mapStyles.ts
import libertyThumb from '../../assets/map-styles/liberty.png'
import brightThumb from '../../assets/map-styles/bright.png'
import positronThumb from '../../assets/map-styles/positron.png'
import darkThumb from '../../assets/map-styles/dark.png'

export interface MapStyleOption {
  id: string
  label: string
  url: string
  thumb: string
}

export const MAP_STYLES: MapStyleOption[] = [
  { id: 'liberty', label: 'Standard', url: 'https://tiles.openfreemap.org/styles/liberty', thumb: libertyThumb },
  { id: 'bright', label: 'Bright', url: 'https://tiles.openfreemap.org/styles/bright', thumb: brightThumb },
  { id: 'positron', label: 'Light', url: 'https://tiles.openfreemap.org/styles/positron', thumb: positronThumb },
  { id: 'dark', label: 'Dark', url: 'https://tiles.openfreemap.org/styles/dark', thumb: darkThumb },
]

export interface ColorOption {
  id: string
  label: string
  hex: string
}

export const ROUTE_COLORS: ColorOption[] = [
  { id: 'indigo', label: 'Electric Indigo', hex: '#536DFE' },
  { id: 'amber', label: 'Amber', hex: '#FFB000' },
  { id: 'cyan', label: 'Arctic Cyan', hex: '#00C2D1' },
  { id: 'midnight', label: 'Midnight Slate', hex: '#292D42' },
]

export const PROGRESS_COLORS: ColorOption[] = [
  { id: 'acid-moss', label: 'Acid Moss', hex: '#A3E635' },
  { id: 'volcanic-canyon', label: 'Volcanic Canyon', hex: '#FF5733' },
  { id: 'glacier-blue', label: 'Glacier Blue', hex: '#00D5FF' },
  { id: 'violet', label: 'Violet', hex: '#9D4EDD' },
]
