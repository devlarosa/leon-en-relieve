(async () => {
  const d = document, $ = (i) => d.getElementById(i), out = {}, sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const errs = []; addEventListener("error", e => errs.push(String(e.message)));
  const cv = d.querySelector("#scene canvas"), r = cv.getBoundingClientRect();
  const click = (x, y) => { for (const t of ["pointerdown", "pointerup"]) cv.dispatchEvent(new PointerEvent(t, { clientX: x, clientY: y, button: 0, pointerId: 7, pointerType: "mouse", bubbles: true })); };
  // 1) comarca
  const sel = $("comarca"); sel.value = "El Páramo"; sel.dispatchEvent(new Event("change", { bubbles: true }));
  await sleep(2500); out.comarca = $("info").hidden ? "oculta" : $("i-name").textContent + " · " + $("i-code").textContent + " municipios";
  // 2) clic en un municipio dentro de la vista
  click(r.left + r.width * 0.6, r.top + r.height * 0.6); await sleep(1500);
  out.municipio = $("info").hidden ? "oculta" : $("i-name").textContent + " · " + $("i-com").textContent;
  // 3) capa histórica y año 1950
  $("l-hist").click(); const a = $("anio"); a.value = 5; a.dispatchEvent(new Event("input", { bubbles: true }));
  await sleep(800); out.hist = $("anio-o").textContent + " · " + $("prov-note").textContent.slice(0, 60);
  // 4) relieve de población (carga diferida)
  const m = $("morph"); m.value = 60; m.dispatchEvent(new Event("input", { bubbles: true }));
  await sleep(4000); out.morph = $("morph-o").textContent;
  m.value = 0; m.dispatchEvent(new Event("input", { bubbles: true })); await sleep(1500);
  out.errores = errs;
  return JSON.stringify(out);
})()
