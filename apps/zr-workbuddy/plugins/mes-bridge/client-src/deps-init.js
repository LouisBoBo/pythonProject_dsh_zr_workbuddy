/** Create shared ctx with React bindings (esbuild entry helper). */
export function createCtx(require) {
  var React = require("react");
  return {
    React: React,
    h: React.createElement,
    useState: React.useState,
    useMemo: React.useMemo,
    useEffect: React.useEffect,
    useLayoutEffect: React.useLayoutEffect || React.useEffect,
    useRef: React.useRef,
    _wbClientCtx: null,
    _loginGateUnmount: null,
  };
}
