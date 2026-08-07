import { createTheme, ThemeProvider } from '@mui/material/styles'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { EnrolSheet } from '../components/EnrolSheet'
import { FirstRunChip } from '../components/FirstRunChip'
import { NamingSheet } from '../components/NamingSheet'
import type { HubPhone } from '../types'

function mkPhone(over: Partial<HubPhone> = {}): HubPhone {
  return {
    phoneId: 'P1',
    person: { name: 'Pixel 8' },
    platform: 'android',
    protocol: 'androidauto',
    presence: { level: 'docked', rank: 3 },
    policy: { autoDock: true },
    ...over
  }
}

function renderWith(node: React.ReactNode) {
  return render(
    <ThemeProvider theme={createTheme({ palette: { mode: 'dark' } })}>{node}</ThemeProvider>
  )
}

describe('NamingSheet', () => {
  it('shows the phone model and a name input', () => {
    renderWith(<NamingSheet phone={mkPhone()} open onClose={() => {}} onRename={() => {}} />)
    expect(screen.getByText(/whose phone is this/i)).toBeInTheDocument()
    expect(screen.getByTestId('hub-naming-input')).toBeInTheDocument()
  })

  it('posts phone.rename with the trimmed name on save', () => {
    const onRename = vi.fn()
    renderWith(<NamingSheet phone={mkPhone()} open onClose={() => {}} onRename={onRename} />)
    fireEvent.change(screen.getByTestId('hub-naming-input'), { target: { value: '  Sarah  ' } })
    fireEvent.click(screen.getByTestId('hub-naming-save'))
    expect(onRename).toHaveBeenCalledWith('P1', 'Sarah')
  })

  it('disable save when the name is empty', () => {
    renderWith(
      <NamingSheet
        phone={mkPhone({ person: { name: '' } })}
        open
        onClose={() => {}}
        onRename={() => {}}
      />
    )
    expect(screen.getByTestId('hub-naming-save')).toBeDisabled()
  })

  it('offers enrollment only when the phone has no companion', () => {
    const { rerender } = renderWith(
      <NamingSheet phone={mkPhone()} open onClose={() => {}} onRename={() => {}} />
    )
    expect(screen.getByTestId('hub-naming-enrol-offer')).toBeInTheDocument()
    rerender(
      <ThemeProvider theme={createTheme({ palette: { mode: 'dark' } })}>
        <NamingSheet
          phone={mkPhone({ companion: { installed: true } })}
          open
          onClose={() => {}}
          onRename={() => {}}
        />
      </ThemeProvider>
    )
    expect(screen.queryByTestId('hub-naming-enrol-offer')).not.toBeInTheDocument()
  })
})

describe('EnrolSheet', () => {
  it('calls onEnrolStart on open and shows the code', async () => {
    const onEnrolStart = vi.fn(async () => ({ code: '123456' }))
    renderWith(<EnrolSheet phone={mkPhone()} open onClose={() => {}} onEnrolStart={onEnrolStart} />)
    await waitFor(() => expect(onEnrolStart).toHaveBeenCalledWith('P1'))
    await waitFor(() => expect(screen.getByTestId('hub-enrol-code')).toHaveTextContent('123456'))
  })

  it('shows an error when no code is returned', async () => {
    const onEnrolStart = vi.fn(async () => ({ code: undefined }))
    renderWith(<EnrolSheet phone={mkPhone()} open onClose={() => {}} onEnrolStart={onEnrolStart} />)
    await waitFor(() => expect(screen.getByTestId('hub-enrol-error')).toBeInTheDocument())
  })
})

describe('FirstRunChip', () => {
  it('shows the naming chip for an unnamed (model-default) phone', () => {
    renderWith(
      <FirstRunChip phone={mkPhone({ person: { name: 'Pixel 8' } })} onRename={() => {}} />
    )
    expect(screen.getByTestId('hub-firstrun-chip')).toHaveTextContent(/whose phone is this/i)
  })

  it('shows the enrol chip when named but no companion', () => {
    renderWith(<FirstRunChip phone={mkPhone({ person: { name: 'Sarah' } })} onRename={() => {}} />)
    expect(screen.getByTestId('hub-firstrun-chip')).toHaveTextContent(/also reach/i)
  })

  it('hides when named and has a companion', () => {
    const { container } = renderWith(
      <FirstRunChip
        phone={mkPhone({ person: { name: 'Sarah' }, companion: { installed: true } })}
        onRename={() => {}}
      />
    )
    expect(container.querySelector('[data-testid="hub-firstrun-chip"]')).toBeNull()
  })

  it('opens the naming sheet on click', () => {
    renderWith(<FirstRunChip phone={mkPhone()} onRename={() => {}} />)
    fireEvent.click(screen.getByTestId('hub-firstrun-chip'))
    expect(screen.getByTestId('hub-naming-sheet')).toBeInTheDocument()
  })

  it('is dismissable', () => {
    const { container } = renderWith(<FirstRunChip phone={mkPhone()} onRename={() => {}} />)
    // MUI Chip renders the delete icon with .MuiChip-deleteIcon.
    const deleteIcon = container.querySelector('.MuiChip-deleteIcon')
    fireEvent.click(deleteIcon as HTMLElement)
    expect(container.querySelector('[data-testid="hub-firstrun-chip"]')).toBeNull()
  })
})
