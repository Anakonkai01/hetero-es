/** Saves an on-screen SVG chart as a PNG (white background, 2x resolution) so it can go straight into a report. */
export async function svgToPngBlob(svg: SVGSVGElement, scale = 2): Promise<Blob> {
  const box = svg.viewBox.baseVal;
  const width = box.width || svg.clientWidth, height = box.height || svg.clientHeight;
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  // Charts use CSS variables for colour; resolve them so the standalone image looks the same as on screen.
  const style = getComputedStyle(svg);
  const resolve = (text: string) => text.replace(/var\((--[a-z0-9-]+)\)/gi, (_whole, name: string) => style.getPropertyValue(name).trim() || "#000");
  clone.querySelectorAll<SVGElement>("*").forEach(element => {
    for (const attribute of ["fill", "stroke"]) {
      const value = element.getAttribute(attribute);
      if (value?.includes("var(")) element.setAttribute(attribute, resolve(value));
    }
  });
  const url = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" }));
  try {
    const image = new Image();
    await new Promise<void>((done, fail) => { image.onload = () => done(); image.onerror = () => fail(new Error("CHART_IMAGE_FAILED")); image.src = url; });
    const canvas = document.createElement("canvas");
    canvas.width = width * scale; canvas.height = height * scale;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("CHART_IMAGE_FAILED");
    context.fillStyle = "#ffffff"; context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    return await new Promise<Blob>((done, fail) => canvas.toBlob(blob => blob ? done(blob) : fail(new Error("CHART_IMAGE_FAILED")), "image/png"));
  } finally { URL.revokeObjectURL(url); }
}

export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = name; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const saveText = (text: string, name: string, type = "text/plain") => saveBlob(new Blob([text], { type: `${type};charset=utf-8` }), name);

/** A file-name-safe version of a run name. */
export function fileStem(name: string): string {
  const plain = name.replace(/đ/g, "d").replace(/Đ/g, "D").normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  return plain.replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "run";
}
