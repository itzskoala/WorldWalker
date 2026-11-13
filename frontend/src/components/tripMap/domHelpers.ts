// domHelpers.ts
export function svgEl<T extends HTMLElement>(markup: string): T {
  const wrap = document.createElement('div')
  wrap.innerHTML = markup.trim()
  return wrap.firstElementChild as T
}

export function onActivate(el: HTMLElement, handler: () => void) {
  el.addEventListener('click', handler)
  el.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' && e.key !== ' ') return
    e.preventDefault()
    handler()
  })
}
