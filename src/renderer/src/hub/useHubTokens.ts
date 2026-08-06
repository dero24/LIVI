// [hub] Resolve the hub palette for the current MUI theme mode. Components call
// this instead of touching colour literals (M11).
import { useTheme } from '@mui/material/styles'
import { type HubTokens, hubTokens } from './tokens'

export function useHubTokens(): HubTokens {
  const theme = useTheme()
  return hubTokens(theme.palette.mode === 'dark' ? 'dark' : 'light')
}
