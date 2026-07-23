import { render, screen } from '@testing-library/react'
import { Home } from '../Home'

describe('Home', () => {
  test('renders the home hub dashboard', () => {
    render(<Home />)

    expect(screen.getByText('Home Hub')).toBeInTheDocument()
    expect(screen.getByText('No phone connected')).toBeInTheDocument()
  })
})
