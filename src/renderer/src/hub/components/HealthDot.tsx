// [hub] Health dot — the honest liveness indicator (§7.6 from the UI side). Goes
// red when hubd stops publishing or its bridge to LIVI drops, so a frozen shell
// is never mistaken for a working one.
import { Box, Tooltip } from '@mui/material'
import { useHubTokens } from '../useHubTokens'

export interface HealthDotProps {
  healthy: boolean
  stale: boolean
}

export function HealthDot({ healthy, stale }: HealthDotProps) {
  const t = useHubTokens()
  const colour = healthy ? t.ok : t.danger
  const label = healthy ? 'Hub online' : stale ? 'Hub not responding' : 'Hub degraded'
  return (
    <Tooltip title={label}>
      <Box
        role="status"
        aria-label={label}
        data-testid="hub-health-dot"
        data-healthy={healthy}
        sx={{
          width: '0.75rem',
          height: '0.75rem',
          borderRadius: '50%',
          backgroundColor: colour,
          boxShadow: healthy ? `0 0 0.4rem ${colour}` : 'none',
          transition: 'background-color 400ms ease, box-shadow 400ms ease',
          flex: '0 0 auto'
        }}
      />
    </Tooltip>
  )
}
