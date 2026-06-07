// Ranges constants for clinical fields
export const RANGES = {
  bloodPressure: {
    systolic: { min: 60, max: 250, normalMin: 90, normalMax: 140 },
    diastolic: { min: 40, max: 150, normalMin: 60, normalMax: 90 },
  },
  weight: { min: 20, max: 300, warningDiff: 5 },
  height: { min: 50, max: 250 },
  age: { min: 18, max: 120 },
  glucose: { min: 30, max: 500, hypo: 70, hyperLow: 140, hyperHigh: 300 },
  bmi: { underweight: 18.5, normal: 24.9, overweight: 29.9 },
}

/**
 * Validate blood pressure values
 * @param {number} systolic
 * @param {number} diastolic
 * @returns {{ valid: boolean, warnings: string[], errors: string[] }}
 */
export function validateBloodPressure(systolic, diastolic) {
  const warnings = []
  const errors = []

  if (!systolic || !diastolic) {
    return { valid: true, warnings: [], errors: [] }
  }

  // Error: systolic must be greater than diastolic
  if (systolic <= diastolic) {
    errors.push('La presión sistólica debe ser mayor que la diastólica')
  }

  // Error: out of measurable range
  if (systolic < RANGES.bloodPressure.systolic.min) {
    errors.push(`Presión sistólica fuera de rango (mínimo ${RANGES.bloodPressure.systolic.min} mmHg)`)
  }
  if (systolic > RANGES.bloodPressure.systolic.max) {
    errors.push(`Presión sistólica fuera de rango (máximo ${RANGES.bloodPressure.systolic.max} mmHg)`)
  }
  if (diastolic < RANGES.bloodPressure.diastolic.min) {
    errors.push(`Presión diastólica fuera de rango (mínimo ${RANGES.bloodPressure.diastolic.min} mmHg)`)
  }
  if (diastolic > RANGES.bloodPressure.diastolic.max) {
    errors.push(`Presión diastólica fuera de rango (máximo ${RANGES.bloodPressure.diastolic.max} mmHg)`)
  }

  // Warnings for very high values
  if (systolic > 180) {
    warnings.push('Presión sistólica muy alta (>180 mmHg) - Crisis hipertensiva')
  }
  if (diastolic > 120) {
    warnings.push('Presión diastólica muy alta (>120 mmHg) - Crisis hipertensiva')
  }

  // Warning for very low values
  if (systolic < 90) {
    warnings.push('Presión sistólica baja (<90 mmHg) - Posible hipotensión')
  }
  if (diastolic < 60) {
    warnings.push('Presión diastólica baja (<60 mmHg) - Posible hipotensión')
  }

  return { valid: errors.length === 0, warnings, errors }
}

/**
 * Validate weight, optionally comparing with last weight
 * @param {number} weight
 * @param {number|null} lastWeight
 * @returns {{ valid: boolean, warnings: string[] }}
 */
export function validateWeight(weight, lastWeight = null) {
  const warnings = []

  if (!weight) {
    return { valid: true, warnings: [] }
  }

  if (weight < RANGES.weight.min) {
    warnings.push(`Peso fuera de rango (mínimo ${RANGES.weight.min} kg)`)
  }
  if (weight > RANGES.weight.max) {
    warnings.push(`Peso fuera de rango (máximo ${RANGES.weight.max} kg)`)
  }

  if (lastWeight && Math.abs(weight - lastWeight) > RANGES.weight.warningDiff) {
    warnings.push(
      `Cambio significativo de peso (${Math.abs(weight - lastWeight).toFixed(1)} kg de diferencia con el último registro)`
    )
  }

  return { valid: true, warnings }
}

/**
 * Validate glucose reading
 * @param {number} glucose
 * @returns {{ valid: boolean, warnings: string[] }}
 */
export function validateGlucose(glucose) {
  const warnings = []

  if (!glucose) {
    return { valid: true, warnings: [] }
  }

  if (glucose > RANGES.glucose.hyperHigh) {
    warnings.push('Glucosa muy alta (>300 mg/dL) - Riesgo de cetoacidosis')
  }
  if (glucose < RANGES.glucose.hypo) {
    warnings.push('Glucosa baja (<70 mg/dL) - Riesgo de hipoglucemia')
  }

  return { valid: true, warnings }
}

/**
 * Calculate BMI from weight (kg) and height (cm)
 * @param {number} weight - Weight in kg
 * @param {number} height - Height in cm
 * @returns {{ bmi: number|null, category: string }}
 */
export function calculateBMI(weight, height) {
  if (!weight || !height || height === 0) {
    return { bmi: null, category: '' }
  }

  const heightM = height / 100
  const bmi = weight / (heightM * heightM)
  const bmiRounded = Math.round(bmi * 10) / 10

  let category = ''
  if (bmi < RANGES.bmi.underweight) {
    category = 'Bajo peso'
  } else if (bmi < RANGES.bmi.normal) {
    category = 'Normal'
  } else if (bmi < RANGES.bmi.overweight) {
    category = 'Sobrepeso'
  } else {
    category = 'Obesidad'
  }

  return { bmi: bmiRounded, category }
}

/**
 * Get risk level color class
 * @param {string} level - 'low', 'medium', 'high'
 * @returns {string}
 */
export function getRiskBadgeClass(level) {
  switch (level?.toLowerCase()) {
    case 'low':
    case 'bajo':
      return 'badge-risk-low'
    case 'medium':
    case 'medio':
      return 'badge-risk-medium'
    case 'high':
    case 'alto':
      return 'badge-risk-high'
    default:
      return 'bg-gray-200 text-gray-700'
  }
}

/**
 * Get risk level label in Spanish
 * @param {string} level
 * @returns {string}
 */
export function getRiskLabel(level) {
  switch (level?.toLowerCase()) {
    case 'low':
      return 'Bajo'
    case 'medium':
      return 'Medio'
    case 'high':
      return 'Alto'
    case 'bajo':
      return 'Bajo'
    case 'medio':
      return 'Medio'
    case 'alto':
      return 'Alto'
    default:
      return level || 'Desconocido'
  }
}
