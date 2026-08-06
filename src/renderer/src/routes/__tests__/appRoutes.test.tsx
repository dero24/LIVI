vi.mock('../../components/pages', () => ({
  Home: () => null,
  Media: () => null,
  Camera: () => null,
  Devices: () => null,
  Maps: () => null,
  Telemetry: () => null
}))
vi.mock('../../components/layouts/Layout', () => ({
  Layout: () => null
}))
vi.mock('../../components/pages/settings/SettingsPage', () => ({
  SettingsPage: () => null
}))
vi.mock('../schemas/schema', () => ({
  settingsRoutes: { children: [{ path: 'general' }] }
}))
vi.mock('../../hub/HubShell', () => ({
  HubShell: () => null
}))

import { appRoutes } from '../appRoutes'

describe('appRoutes', () => {
  test('contains expected top-level app routes', async () => {
    const root = appRoutes[0]
    const paths = (root.children ?? []).map((r: any) => r.path)
    expect(paths).toEqual(['/home', '/telemetry', '/cluster', '/media', '/camera', '/settings/*'])
  })

  test('exposes the additive /hub route alongside the Layout root', async () => {
    const topLevelPaths = appRoutes.map((r: any) => r.path)
    expect(topLevelPaths).toContain('/hub')
    // The Layout root stays first so nothing that indexes appRoutes[0] regresses.
    expect(appRoutes[0].path).toBe('/')
  })

  test('falls back to empty settings children when settingsRoutes is missing', async () => {
    vi.resetModules()

    vi.doMock('../../components/pages', () => ({
      Home: () => null,
      Media: () => null,
      Camera: () => null,
      Devices: () => null,
      Maps: () => null,
      Telemetry: () => null
    }))
    vi.doMock('../../components/layouts/Layout', () => ({
      Layout: () => null
    }))
    vi.doMock('../../components/pages/settings/SettingsPage', () => ({
      SettingsPage: () => null
    }))
    vi.doMock('../schemas/schema', () => ({
      settingsRoutes: undefined
    }))

    const { appRoutes: isolatedAppRoutes } = await import('../appRoutes')
    const root = isolatedAppRoutes[0]
    const settingsRoute = root.children.find((r: any) => r.path === '/settings/*')

    expect(settingsRoute.children).toEqual([])

    vi.doUnmock('../../components/pages')
    vi.doUnmock('../../components/layouts/Layout')
    vi.doUnmock('../../components/pages/settings/SettingsPage')
    vi.doUnmock('../schemas/schema')
  })
})
