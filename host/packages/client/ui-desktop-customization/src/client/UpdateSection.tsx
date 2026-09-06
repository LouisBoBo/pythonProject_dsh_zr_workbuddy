/** Visible update center backed by the Electron main-process updater. */

import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import type { DesktopRendererBridge, DesktopUpdateState } from './bridge.ts'
import css from './DesktopCustomization.module.css'

export interface UpdateSectionInjected {
  readonly bridge: DesktopRendererBridge | undefined
}

export type UpdateSectionProps = Partial<UpdateSectionInjected>

/** Render the installed version and the temporarily unavailable online-update state. */
export function UpdateSection({ bridge }: UpdateSectionProps): ReactNode {
  const [state, setState] = useState<DesktopUpdateState | undefined>(undefined)
  useEffect(() => {
    if (bridge === undefined) return
    let active = true
    void bridge.updates.getState().then((next) => { if (active) setState(next) })
    return () => { active = false }
  }, [bridge])

  return (
    <section className={css.section}>
      <div>
        <h2 className={css.title}>软件更新</h2>
        <p className={css.intro}>在线更新暂未开放。需要更新时，请暂时从软件发布页下载最新安装包。</p>
      </div>
      <div className={css.updateCard}>
        <div className={css.updateIcon}>DSH</div>
        <div className={css.updateIdentity}>
          <strong>DeepSeek Harness Desktop</strong>
          <span>当前版本 {state?.currentVersion ?? '读取中…'}</span>
        </div>
        <span className={css.statusPill}>暂未开放</span>
      </div>
      <div className={css.actions}>
        <button type="button" className={css.primaryButton} disabled>在线更新暂未开放</button>
      </div>
    </section>
  )
}
