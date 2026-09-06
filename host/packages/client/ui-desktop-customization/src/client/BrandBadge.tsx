/** Persistent team attribution in the shell overlay. */

import type { ReactNode } from 'react'
import css from './DesktopCustomization.module.css'

/** Render the clickable team badge. */
export function BrandBadge(): ReactNode {
  return (
    <a
      className={css.brandBadge}
      href="https://www.beyondata.com/"
      target="_blank"
      rel="noreferrer"
      aria-label="访问赋范空间官网"
      title="赋范空间出品"
    >
      <img src="/dsh-desktop/beyondata-logo.png" alt="" />
      <span>赋范空间出品</span>
    </a>
  )
}

