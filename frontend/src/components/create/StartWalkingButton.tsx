interface StartWalkingButtonProps {
  disabled: boolean
  checking: boolean
  onClick: () => void
}

export function StartWalkingButton({ disabled, checking, onClick }: StartWalkingButtonProps) {
  return (
    <button type="button" className="btn btn-start" id="start-btn" disabled={disabled} onClick={onClick}>
      {checking ? (
        <>
          <span className="spinner spinner-sm" aria-hidden="true" />
          Checking route…
        </>
      ) : (
        <>
          <svg className="icon" viewBox="0 0 24 24" fill="none">
            <circle cx="11" cy="11" r="7" stroke="currentColor" strokeWidth="2" />
            <path d="m21 21-4.3-4.3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          Start Walking
        </>
      )}
    </button>
  )
}
