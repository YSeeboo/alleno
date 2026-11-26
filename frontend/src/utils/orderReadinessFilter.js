export const unknownGap = line => line.gap === null || line.gap === undefined || line.gap === '' || !Number.isFinite(Number(line.gap))
export const needsPreparation = line => unknownGap(line) || Number(line.gap) !== 0
export const filterOrderLines = (lines, mode) => mode === 'pending' ? lines.filter(needsPreparation) : lines
