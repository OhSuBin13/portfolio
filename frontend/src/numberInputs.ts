export const normalizeNumericInput = (value: string) => value.replaceAll(",", "").trim()

export const parseRequiredNumber = (value: string) => Number(normalizeNumericInput(value))
