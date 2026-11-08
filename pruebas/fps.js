new Promise(res => { let n = 0; const t0 = performance.now();
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "q" }));
  const f = () => { n++; if (performance.now() - t0 < 6000) requestAnimationFrame(f); else { window.dispatchEvent(new KeyboardEvent("keyup", { key: "q" })); res(JSON.stringify({ fps_girando: +(n / 6).toFixed(1) })); } };
  requestAnimationFrame(f); })
