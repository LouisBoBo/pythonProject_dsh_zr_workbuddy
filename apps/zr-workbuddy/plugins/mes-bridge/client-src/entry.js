import { createCtx } from './deps-init.js';
import { installPreamble } from './shared-preamble.js';
import { installCss } from './css.js';
import { installSharedHelpers } from './shared-helpers.js';
import { installCodeReview } from './lanes/code-review.js';
import { installCodeCommit } from './lanes/code-commit.js';
import { installCodeDev } from './lanes/code-dev.js';
import { installCodeDeploy } from './lanes/code-deploy.js';
import { installSettings } from './settings.js';
import { installUsageHelpers } from './usage-helpers.js';
import { installLogin } from './login.js';
import { installUsageSection } from './usage-section.js';
import { installSpace } from './space.js';
import { installUsageView } from './usage-view.js';
import { installLoginMount } from './login-mount.js';
import { installApply } from './apply.js';

export function createBridgeModule(require) {
  var ctx = createCtx(require);
  installPreamble(ctx);
  installCss(ctx);
  installSharedHelpers(ctx);
  installCodeReview(ctx);
  installCodeCommit(ctx);
  installCodeDev(ctx);
  installCodeDeploy(ctx);
  installSettings(ctx);
  installUsageHelpers(ctx);
  installLogin(ctx);
  installUsageSection(ctx);
  installSpace(ctx);
  installUsageView(ctx);
  installLoginMount(ctx);
  installApply(ctx);
  return { inject: ['slots'], apply: ctx.apply };
}
