import React from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
} from 'recharts'
import { Activity } from 'lucide-react'

export default function GlucoseChart({ readings = [] }) {
  if (!readings || readings.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-gray-400">
        <Activity className="w-8 h-8 mb-2" />
        <p className="text-sm">Sin lecturas de glucosa disponibles</p>
      </div>
    )
  }

  // Format readings for chart
  const chartData = readings
    .map((reading) => ({
      date: reading.measurement_timestamp || reading.timestamp || reading.created_at || reading.measured_at,
      value: reading.glucose_mg_dl || reading.glucose_level || reading.value || reading.glucose || 0,
      id: reading.id,
    }))
    .filter((d) => d.value > 0)
    .sort((a, b) => new Date(a.date) - new Date(b.date))

  if (chartData.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-gray-400">
        <Activity className="w-8 h-8 mb-2" />
        <p className="text-sm">Sin datos de glucosa válidos</p>
      </div>
    )
  }

  // Calculate Y axis domain
  const minValue = Math.min(...chartData.map((d) => d.value))
  const maxValue = Math.max(...chartData.map((d) => d.value))
  const yMin = Math.max(0, Math.floor((minValue - 20) / 10) * 10)
  const yMax = Math.ceil((maxValue + 20) / 10) * 10

  // Format X axis ticks
  const formatXAxis = (dateStr) => {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    return date.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit' })
  }

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const data = payload[0]
      const date = new Date(label)
      let zone = 'Normal'
      let zoneColor = '#47805a'
      if (data.value < 70) {
        zone = 'Hipoglucemia'
        zoneColor = '#2c5282'
      } else if (data.value > 300) {
        zone = 'Muy Alta'
        zoneColor = '#8e4f49'
      } else if (data.value > 140) {
        zone = 'Elevada'
        zoneColor = '#9b8048'
      }

      return (
        <div className="bg-white shadow-lg rounded-lg border border-gray-200 p-3 text-xs">
          <p className="text-gray-500 mb-1">
            {date.toLocaleString('es-ES')}
          </p>
          <p className="font-semibold text-gray-800">
            {data.value.toFixed(0)} mg/dL
          </p>
          <p style={{ color: zoneColor }} className="font-medium">
            {zone}
          </p>
        </div>
      )
    }
    return null
  }

  return (
    <div className="w-full">
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />

          {/* Color-coded zones */}
          <ReferenceArea y1={70} y2={140} fill="#47805a" fillOpacity={0.05} />
          <ReferenceArea y1={140} y2={300} fill="#9b8048" fillOpacity={0.05} />
          <ReferenceArea y1={300} y2={yMax} fill="#8e4f49" fillOpacity={0.05} />
          <ReferenceArea y1={yMin} y2={70} fill="#2c5282" fillOpacity={0.05} />

          {/* Reference lines */}
          <ReferenceLine
            y={70}
            stroke="#2c5282"
            strokeDasharray="5 5"
            strokeWidth={1}
            label={{
              value: 'Hipoglucemia (70)',
              position: 'left',
              fill: '#2c5282',
              fontSize: 10,
            }}
          />
          <ReferenceLine
            y={140}
            stroke="#9b8048"
            strokeDasharray="5 5"
            strokeWidth={1}
            label={{
              value: 'Normal max (140)',
              position: 'left',
              fill: '#9b8048',
              fontSize: 10,
            }}
          />
          <ReferenceLine
            y={300}
            stroke="#8e4f49"
            strokeDasharray="5 5"
            strokeWidth={1}
            label={{
              value: 'Hiperglucemia (300)',
              position: 'right',
              fill: '#8e4f49',
              fontSize: 10,
            }}
          />

          <XAxis
            dataKey="date"
            tickFormatter={formatXAxis}
            tick={{ fontSize: 10 }}
            stroke="#cbd5e0"
          />
          <YAxis
            domain={[yMin, yMax]}
            tick={{ fontSize: 10 }}
            stroke="#cbd5e0"
            tickFormatter={(v) => `${v}`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#2c5282"
            strokeWidth={2}
            dot={{ fill: '#2c5282', strokeWidth: 0, r: 3 }}
            activeDot={{ r: 5, fill: '#2c5282', stroke: '#fff', strokeWidth: 2 }}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center justify-center gap-6 mt-2 text-[10px] text-gray-500">
        <div className="flex items-center gap-1">
          <div className="w-3 h-1.5 rounded bg-[#2c5282] opacity-30" />
          <span>Hipoglucemia (&lt;70)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-1.5 rounded bg-[#47805a] opacity-30" />
          <span>Normal (70-140)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-1.5 rounded bg-[#9b8048] opacity-30" />
          <span>Elevada (140-300)</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-1.5 rounded bg-[#8e4f49] opacity-30" />
          <span>Muy Alta (&gt;300)</span>
        </div>
      </div>
    </div>
  )
}