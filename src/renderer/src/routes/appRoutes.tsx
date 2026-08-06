import { Layout } from '../components/layouts/Layout'
import { Camera, Home, Media, Telemetry } from '../components/pages'
import { SettingsPage } from '../components/pages/settings/SettingsPage'
import { HubShell } from '../hub/HubShell'
import { settingsRoutes } from './schemas/schema'
import { RoutePath } from './types'

export const appRoutes = [
  {
    path: '/',
    element: <Layout />,
    children: [
      {
        path: `/${RoutePath.Home}`,
        element: <Home />
      },
      {
        path: `/${RoutePath.Telemetry}`,
        element: <Telemetry />
      },
      {
        path: `/${RoutePath.Cluster}`,
        element: <></>
      },
      {
        path: `/${RoutePath.Media}`,
        element: <Media />
      },
      {
        path: `/${RoutePath.Camera}`,
        element: <Camera />
      },
      {
        path: `/${RoutePath.Settings}/*`,
        element: <SettingsPage />,
        children: settingsRoutes?.children ?? []
      }
    ]
  },
  {
    // [hub] Phase 1.8 (M9): the HubShell surface, full-bleed and outside LIVI's
    // nav Layout. Additive today (reachable at /hub); the destructive root-swap
    // that makes this the ONLY reachable surface lands with projection-plane
    // coexistence (§12.2), so the working projection is never put at risk.
    path: `/${RoutePath.Hub}`,
    element: <HubShell />
  }
]
