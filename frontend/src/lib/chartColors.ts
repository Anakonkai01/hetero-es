const COMPARE_COLORS = ["var(--acc)", "var(--chart-secondary)", "#c2410c", "#7c3aed", "#0e7490"];
export const compareColor = (index: number) => COMPARE_COLORS[index % COMPARE_COLORS.length];
