// [hub] A minimal on-screen keyboard for the touchscreen kiosk. The
// livi-compositor does not expose the Wayland virtual-keyboard protocol,
// so squeekboard cannot be used. This component renders a simple QWERTY
// layout directly in the renderer and calls back on each key press.
// Designed for short text entry (names, not essays): letters, space,
// backspace, and a shift toggle. No autocomplete, no swiping, no emoji.
import { Box, Button } from '@mui/material'
import { useState } from 'react'
import { useHubTokens } from '../useHubTokens'

export interface TouchKeyboardProps {
  onKey: (key: string) => void
  onBackspace: () => void
  onEnter?: () => void
  sx?: object
}

const ROWS_LOWER = [
  'qwertyuiop',
  'asdfghjkl',
  'zxcvbnm'
]

const ROWS_UPPER = [
  'QWERTYUIOP',
  'ASDFGHJKL',
  'ZXCVBNM'
]

export function TouchKeyboard({ onKey, onBackspace, onEnter, sx }: TouchKeyboardProps) {
  const t = useHubTokens()
  const [shift, setShift] = useState(false)
  const rows = shift ? ROWS_UPPER : ROWS_LOWER

  const keyBtn = (label: string, onPress: () => void, wide?: number) => (
    <Button
      onClick={onPress}
      sx={{
        minWidth: wide ? `${wide * 2.6}rem` : '2.6rem',
        height: '2.6rem',
        fontSize: '1.1rem',
        fontWeight: 500,
        color: t.text,
        backgroundColor: t.surfaceMuted,
        border: `1px solid ${t.border}`,
        borderRadius: '8px',
        textTransform: 'none',
        padding: 0,
        flex: wide ? wide : 1,
        '&:active': {
          backgroundColor: t.border,
          transform: 'scale(0.95)'
        },
        transition: 'transform 80ms, background-color 80ms'
      }}
    >
      {label}
    </Button>
  )

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', ...(sx ?? {}) }}>
      {rows.map((row, i) => (
        <Box key={i} sx={{ display: 'flex', gap: '0.3rem', justifyContent: 'center' }}>
          {i === 2 && keyBtn('⇧', () => setShift((s) => !s), 1.5)}
          {row.split('').map((ch) => (
            <Box key={ch}>
              {keyBtn(ch, () => {
                onKey(ch)
                if (shift) setShift(false)
              })}
            </Box>
          ))}
          {i === 2 && keyBtn('⌫', onBackspace, 1.5)}
        </Box>
      ))}
      <Box sx={{ display: 'flex', gap: '0.3rem', justifyContent: 'center' }}>
        {keyBtn(' ', () => onKey(' '), 5)}
        {onEnter && keyBtn('Done', onEnter, 2)}
      </Box>
    </Box>
  )
}
