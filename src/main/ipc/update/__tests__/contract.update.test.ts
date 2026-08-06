/**
 * Contract tests — update feed and asset picker
 *
 * These tests assert the update feed contract from §11.4.
 * They test *upstream's* behaviour, not ours.
 *
 * Guards: §11.4
 */
import { releaseFeedUrl } from '@main/ipc/update/feed'
import { pickAssetForPlatform } from '@main/ipc/update/pickAsset'

describe('contract.update', () => {
  describe('releaseFeedUrl() honours UPDATE_REPO (§11.4)', () => {
    const feed = process.env.UPDATE_FEED
    const repo = process.env.UPDATE_REPO

    beforeEach(() => {
      delete process.env.UPDATE_FEED
      delete process.env.UPDATE_REPO
    })

    afterEach(() => {
      if (feed === undefined) delete process.env.UPDATE_FEED
      else process.env.UPDATE_FEED = feed
      if (repo === undefined) delete process.env.UPDATE_REPO
      else process.env.UPDATE_REPO = repo
    })

    it('defaults to f-io/LIVI', () => {
      expect(releaseFeedUrl(false)).toBe('https://api.github.com/repos/f-io/LIVI/releases/latest')
      expect(releaseFeedUrl(true)).toBe(
        'https://api.github.com/repos/f-io/LIVI/releases/tags/nightly'
      )
    })

    it('honours UPDATE_REPO for a fork', () => {
      process.env.UPDATE_REPO = 'dero24/LIVI'
      expect(releaseFeedUrl(false)).toBe('https://api.github.com/repos/dero24/LIVI/releases/latest')
      expect(releaseFeedUrl(true)).toBe(
        'https://api.github.com/repos/dero24/LIVI/releases/tags/nightly'
      )
    })

    it('UPDATE_FEED overrides everything', () => {
      process.env.UPDATE_REPO = 'dero24/LIVI'
      process.env.UPDATE_FEED = 'https://example.test/feed.json'
      expect(releaseFeedUrl(false)).toBe('https://example.test/feed.json')
      expect(releaseFeedUrl(true)).toBe('https://example.test/feed.json')
    })
  })

  describe('pickAssetForPlatform matches our arm64 artifact name (§11.4)', () => {
    const platform = process.platform
    const arch = process.arch

    beforeEach(() => {
      Object.defineProperty(process, 'platform', { value: platform })
      Object.defineProperty(process, 'arch', { value: arch })
    })

    it('matches LIVI-<version>-linux-arm64.AppImage on linux arm64', () => {
      Object.defineProperty(process, 'platform', { value: 'linux' })
      Object.defineProperty(process, 'arch', { value: 'arm64' })

      const result = pickAssetForPlatform([
        { name: 'LIVI-8.0.0-linux-x86_64.AppImage', browser_download_url: 'https://example.com/x64' } as never,
        { name: 'LIVI-8.0.0-linux-arm64.AppImage', browser_download_url: 'https://example.com/arm64' } as never
      ])

      expect(result).toEqual({ url: 'https://example.com/arm64' })
    })

    it('matches aarch64 variant on linux arm64', () => {
      Object.defineProperty(process, 'platform', { value: 'linux' })
      Object.defineProperty(process, 'arch', { value: 'arm64' })

      const result = pickAssetForPlatform([
        { name: 'LIVI-8.0.0-linux-x86_64.AppImage', browser_download_url: 'https://example.com/x64' } as never,
        { name: 'LIVI-8.0.0-linux-aarch64.AppImage', browser_download_url: 'https://example.com/aarch64' } as never
      ])

      expect(result).toEqual({ url: 'https://example.com/aarch64' })
    })

    it('matches x86_64 variant on linux x64', () => {
      Object.defineProperty(process, 'platform', { value: 'linux' })
      Object.defineProperty(process, 'arch', { value: 'x64' })

      const result = pickAssetForPlatform([
        { name: 'LIVI-8.0.0-linux-arm64.AppImage', browser_download_url: 'https://example.com/arm64' } as never,
        { name: 'LIVI-8.0.0-linux-x86_64.AppImage', browser_download_url: 'https://example.com/x64' } as never
      ])

      expect(result).toEqual({ url: 'https://example.com/x64' })
    })
  })
})
