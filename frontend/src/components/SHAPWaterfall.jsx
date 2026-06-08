import React from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts'

/**
 * SHAP Waterfall Chart — shows how each feature pushes the prediction
 * from the base value (expected value) to the final prediction.
 *
 * Each bar represents a feature's contribution:
 *  - Red/warm bars = increase risk (positive SHAP value)
 *  - Green/cool bars = decrease risk (negative SHAP value)
 *  - Indigo bar = final prediction
 *  - Grey bar = base value
 *
 * Features are sorted by absolute SHAP value (most important first).
 *
 * Uses a stacked bar approach where:
 *  - First (invisible) bar = offset from 0 to start of visible segment
 *  - Second (visible) bar = height of the contribution segment
 */
export default function SHAPWaterfall({ explanation, height = 420 }) {
  if (!explanation) return null

  const { shap_values = {}, base_value = 0, prediction = 0, feature_meta = {} } = explanation

  // Sort features by absolute SHAP value (descending)
  const sortedFeatures = Object.entries(shap_values)
    .sort(([, a], [, b]) => Math.abs(b) - Math.abs(a))

  // Build waterfall data with proper stacked bar fields
  let cumulative = base_value
  const waterfallData = []

  // Base value bar (from 0 to base_value)
  waterfallData.push({
    feature: '__base__',
    label: 'Valor base (E[f])',
    offset: 0,                                    // invisible offset
    barHeight: base_value,                         // visible bar height
    value: base_value,
    direction: 'base',
  })

  // Feature contribution bars
  sortedFeatures.forEach(([feature, shapVal]) => {
    const start = cumulative
    cumulative += shapVal
    const end = cumulative
    const meta = feature_meta[feature] || {}
    waterfallData.push({
      feature,
      label: meta.label || feature,
      offset: Math.min(start, end),               // invisible offset (lower bound)
      barHeight: Math.abs(end - start),            // visible bar height (always positive)
      value: shapVal,
      direction: shapVal >= 0 ? 'increases' : 'decreases',
      rawStart: start,
      rawEnd: end,
    })
  })

  // Final prediction bar (from 0 to prediction)
  waterfallData.push({
    feature: '__prediction__',
    label: 'Predicción final',
    offset: 0,                                    // invisible offset
    barHeight: prediction,                         // visible bar height
    value: prediction,
    direction: 'final',
  })

  const formatPct = (val) => `${(val * 100).toFixed(1)}%`

  const CustomTooltip = ({ active, payload }) => {
    if (!active || !payload?.length) return null
    const data = payload[0].payload
    if (!data) return null

    return (
      <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-sm max-w-xs">
        <p className="font-semibold text-gray-800 mb-1">{data.label}</p>
        {data.direction === 'base' ? (
          <p className="text-gray-600">
            Valor base: <strong>{formatPct(data.value)}</strong>
          </p>
        ) : data.direction === 'final' ? (
          <p className="text-gray-600">
            Predicción: <strong>{formatPct(data.value)}</strong>
          </p>
        ) : (
          <>
            <p className="text-gray-600">
              Contribución: <strong className={data.value >= 0 ? 'text-red-600' : 'text-green-600'}>
                {data.value >= 0 ? '+' : ''}{(data.value * 100).toFixed(2)} pp
              </strong>
            </p>
            <p className="text-gray-500 text-xs mt-1">
              {data.value >= 0 ? '↑ Aumenta el riesgo' : '↓ Reduce el riesgo'}
            </p>
            <p className="text-gray-500 text-xs">
              Rango: {formatPct(data.rawStart)} → {formatPct(data.rawEnd)}
            </p>
          </>
        )}
      </div>
    )
  }

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart
          data={waterfallData}
          layout="vertical"
          margin={{ top: 10, right: 40, left: 10, bottom: 10 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" horizontal={false} />
          <XAxis
            type="number"
            domain={['dataMin - 0.05', 'dataMax + 0.05']}
            tickFormatter={formatPct}
            tick={{ fontSize: 11 }}
          />
          <YAxis
            dataKey="label"
            type="category"
            tick={{ fontSize: 11 }}
            width={150}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine x={base_value} stroke="#666" strokeDasharray="4 4" />
          {/* Invisible offset bar */}
          <Bar dataKey="offset" stackId="stack" fill="transparent" />
          {/* Visible contribution bar */}
          <Bar dataKey="barHeight" stackId="stack" radius={[0, 3, 3, 0]} barSize={18}>
            {waterfallData.map((entry, index) => (
              <Cell
                key={index}
                fill={
                  entry.direction === 'base'
                    ? '#94a3b8'
                    : entry.direction === 'final'
                    ? '#6366f1'
                    : entry.value >= 0
                    ? '#ef4444'
                    : '#22c55e'
                }
                fillOpacity={
                  entry.direction === 'base' || entry.direction === 'final' ? 0.8 : 0.85
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-red-500" />
          <span>Incrementa riesgo</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-green-500" />
          <span>Reduce riesgo</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-indigo-500" />
          <span>Predicción final</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-gray-400" />
          <span>Valor base</span>
        </div>
      </div>
    </div>
  )
}
