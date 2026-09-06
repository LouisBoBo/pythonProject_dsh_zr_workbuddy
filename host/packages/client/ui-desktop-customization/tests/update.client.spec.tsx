// @vitest-environment jsdom

import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { DesktopRendererBridge } from '../src/client/bridge.ts'
import { UpdateSection } from '../src/client/UpdateSection.tsx'

afterEach(cleanup)

describe('Desktop online updates', () => {
  it('shows the installed version while keeping every online-update action disabled', async () => {
    const check = vi.fn()
    const download = vi.fn()
    const install = vi.fn()
    const onState = vi.fn()
    const bridge = {
      updates: {
        getState: vi.fn(async () => ({ phase: 'up-to-date', currentVersion: '0.1.0-rc.7' })),
        check,
        download,
        install,
        onState,
      },
    } as unknown as DesktopRendererBridge

    render(<UpdateSection bridge={bridge} />)
    await act(async () => {})

    expect(screen.getByText('当前版本 0.1.0-rc.7')).toBeTruthy()
    expect(screen.getByText('暂未开放')).toBeTruthy()
    const button = screen.getByRole('button', { name: '在线更新暂未开放' })
    expect(button.hasAttribute('disabled')).toBe(true)
    fireEvent.click(button)
    expect(check).not.toHaveBeenCalled()
    expect(download).not.toHaveBeenCalled()
    expect(install).not.toHaveBeenCalled()
    expect(onState).not.toHaveBeenCalled()
  })
})
