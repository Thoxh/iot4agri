'use client'

import { useEffect, useState } from 'react'
import { CartesianGrid, Line, LineChart, XAxis, YAxis, ReferenceArea } from 'recharts'
import { supabase } from '@/lib/supabase'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from '@/components/ui/chart'
import Link from 'next/link'

type SensorData = {
  timestamp: string
  ph: number | null
  ph_voltage: number | null
  temp1: number | null
  temp2: number | null
  bme_temperature: number | null
  bme_humidity: number | null
  bme_pressure: number | null
  bme_gas_resistance: number | null
  methan_raw: string[] | null
  methane_ppm: number | null
  methane_percent: number | null
  methane_temperature: number | null
  methane_faults: string[] | null
}

type ChartDataPoint = {
  timestamp: string
  date: string
  ph?: number
  ph_voltage?: number
  temp1?: number
  temp2?: number
  bme_temperature?: number
  bme_humidity?: number
  bme_pressure?: number
  bme_gas_resistance?: number
  methane_ppm?: number
  methane_percent?: number
  methane_temperature?: number
}

type AlarmZone = {
  min: number
  max: number
  label: string
  color: string
}

// Alarm definitions
const ALARM_ZONES = {
  tank_temperature: [
    { min: 0, max: 30, label: 'Too cold (<30°C)', color: '#3b82f6' },
    { min: 30, max: 40, label: 'Optimal (30-40°C)', color: '#22c55e' },
    { min: 40, max: 80, label: 'Too hot (>40°C)', color: '#ef4444' }
  ],
  ph: [
    { min: 0, max: 6, label: 'Too acidic (<6)', color: '#ef4444' },
    { min: 6, max: 8, label: 'Optimal (6-8)', color: '#22c55e' },
    { min: 8, max: 14, label: 'Too alkaline (>8)', color: '#ef4444' }
  ]
}

export default function ChartsPage() {
  const [data, setData] = useState<SensorData[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const { data: sensorData, error } = await supabase
          .from('sensor_data')
          .select('*')
          .order('timestamp', { ascending: false }) // Get newest first

        if (error) {
          console.error('Error fetching sensor data:', error)
          return
        }

        // Reverse the data to show chronological order in charts (oldest to newest)
        const chronologicalData = (sensorData || []).reverse()
        setData(chronologicalData)
      } catch (error) {
        console.error('Error:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  // Format timestamp for display
  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp)
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  // Transform data for charts
  const chartData: ChartDataPoint[] = data.map(point => ({
    timestamp: formatTimestamp(point.timestamp),
    date: new Date(point.timestamp).toLocaleDateString('en-US'),
    ph: point.ph ?? undefined,
    ph_voltage: point.ph_voltage ?? undefined,
    temp1: point.temp1 ?? undefined,
    temp2: point.temp2 ?? undefined,
    bme_temperature: point.bme_temperature ?? undefined,
    bme_humidity: point.bme_humidity ?? undefined,
    bme_pressure: point.bme_pressure ?? undefined,
    bme_gas_resistance: point.bme_gas_resistance ?? undefined,
    methane_ppm: point.methane_ppm ?? undefined,
    methane_percent: point.methane_percent ?? undefined,
    methane_temperature: point.methane_temperature ?? undefined,
  }))

  if (loading) {
    return (
      <main className="flex items-center justify-center min-h-screen">
        <div className="text-gray-500 text-lg">Loading sensor data...</div>
      </main>
    )
  }

  if (data.length === 0) {
    return (
      <main className="flex items-center justify-center min-h-screen">
        <div className="text-gray-500 text-lg">No sensor data available</div>
      </main>
    )
  }

  return (
    <main className="min-h-screen bg-gray-50 p-4 flex justify-center">
      <div className="container mx-auto max-w-7xl">
        <div className="bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden mb-6">
          {/* Header */}
          <div className="bg-green-400 text-white p-4 md:p-6">
            <div className="flex justify-between items-center mb-2">
              <h1 className="text-xl md:text-2xl font-bold">
                📊 Sensor Data Charts
              </h1>
              <Link 
                href="/" 
                className="bg-green-400 hover:bg-green-500 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-colors duration-200"
              >
                🏠 Dashboard
              </Link>
            </div>
            <p className="text-green-100 text-sm">
              Interactive visualization of all biodigester sensor measurements • {data.length} data points
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
          {/* pH Values */}
          <SensorChart
            title="pH Value"
            description="pH level over time"
            data={chartData}
            dataKeys={['ph']}
            config={{
              ph: {
                label: 'pH Value',
                color: '#3b82f6',
              },
            }}
            alarmZones={ALARM_ZONES.ph}
          />

          {/* Tank Temperatures */}
          <SensorChart
            title="Tank Temperatures"
            description="Temperature 1 & 2 in tank"
            data={chartData}
            dataKeys={['temp1', 'temp2']}
            config={{
              temp1: {
                label: 'Temperature 1 (°C)',
                color: '#ef4444',
              },
              temp2: {
                label: 'Temperature 2 (°C)',
                color: '#f97316',
              },
            }}
            alarmZones={ALARM_ZONES.tank_temperature}
            domain={[0, 80]}
          />

          {/* Gas Temperatures */}
          <SensorChart
            title="Gas Temperatures"
            description="BME & Methane temperature sensors"
            data={chartData}
            dataKeys={['bme_temperature', 'methane_temperature']}
            config={{
              bme_temperature: {
                label: 'BME Temperature (°C)',
                color: '#eab308',
              },
              methane_temperature: {
                label: 'Methane Temperature (°C)',
                color: '#22c55e',
              },
            }}
          />

          {/* BME Humidity */}
          <SensorChart
            title="Humidity"
            description="BME sensor humidity"
            data={chartData}
            dataKeys={['bme_humidity']}
            config={{
              bme_humidity: {
                label: 'Humidity (%)',
                color: '#06b6d4',
              },
            }}
          />

          {/* BME Pressure */}
          <SensorChart
            title="Air Pressure"
            description="BME sensor air pressure"
            data={chartData}
            dataKeys={['bme_pressure']}
            config={{
              bme_pressure: {
                label: 'Air Pressure (hPa)',
                color: '#8b5cf6',
              },
            }}
            autoScale={true}
          />

          {/* BME Gas Resistance */}
          <SensorChart
            title="Gas Resistance"
            description="BME sensor gas resistance"
            data={chartData}
            dataKeys={['bme_gas_resistance']}
            config={{
              bme_gas_resistance: {
                label: 'Gas Resistance (kΩ)',
                color: '#10b981',
              },
            }}
          />

          {/* Methane Measurements */}
          <SensorChart
            title="Methane Measurements"
            description="Methane PPM and percentage"
            data={chartData}
            dataKeys={['methane_ppm', 'methane_percent']}
            config={{
              methane_ppm: {
                label: 'Methane (ppm)',
                color: '#f59e0b',
              },
              methane_percent: {
                label: 'Methane (%)',
                color: '#ec4899',
              },
            }}
          />
        </div>
      </div>
    </main>
  )
}

function SensorChart({
  title,
  description,
  data,
  dataKeys,
  config,
  domain,
  autoScale,
  alarmZones,
}: {
  title: string
  description: string
  data: ChartDataPoint[]
  dataKeys: string[]
  config: ChartConfig
  domain?: [number, number]
  autoScale?: boolean
  alarmZones?: AlarmZone[]
}) {
  // Filter data that has at least one value for the desired keys
  const filteredData = data.filter(point => 
    dataKeys.some(key => point[key as keyof ChartDataPoint] !== undefined)
  )

  if (filteredData.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-[300px] text-gray-500">
            No data available
          </div>
        </CardContent>
      </Card>
    )
  }

  // Calculate automatic Y-axis ranges if autoScale is enabled
  let yAxisDomain: [number, number] | undefined = domain
  
  if (autoScale && filteredData.length > 0) {
    const allValues: number[] = []
    dataKeys.forEach(key => {
      filteredData.forEach(point => {
        const value = point[key as keyof ChartDataPoint] as number
        if (typeof value === 'number' && !isNaN(value)) {
          allValues.push(value)
        }
      })
    })
    
    if (allValues.length > 0) {
      const min = Math.min(...allValues)
      const max = Math.max(...allValues)
      const range = max - min
      const padding = range * 0.1 // 10% padding above and below
      yAxisDomain = [min - padding, max + padding]
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>
          {description} • {filteredData.length} data points
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={config} className="h-[300px] w-full">
          <LineChart
            accessibilityLayer
            data={filteredData}
            margin={{
              left: 12,
              right: 12,
              top: 12,
              bottom: 12,
            }}
          >
            <CartesianGrid vertical={false} />
            {alarmZones && alarmZones.map((zone, index) => (
              <ReferenceArea
                key={index}
                y1={zone.min}
                y2={zone.max}
                fill={zone.color}
                fillOpacity={0.3}
                stroke="none"
              />
            ))}
            <XAxis
              dataKey="timestamp"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              minTickGap={32}
              tickFormatter={(value) => {
                const date = new Date(value)
                return date.toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                })
              }}
            />
            <YAxis
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              tickFormatter={(value) => {
                if (typeof value === 'number') {
                  return value.toFixed(1)
                }
                return value
              }}
              domain={yAxisDomain}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  className="w-[200px]"
                  labelFormatter={(value) => {
                    return new Date(value).toLocaleString('en-US', {
                      month: 'short',
                      day: 'numeric',
                      year: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  }}
                  formatter={(value, name) => [
                    typeof value === 'number' ? value.toFixed(2) : value,
                    config[name as keyof typeof config]?.label || name
                  ]}
                />
              }
            />
            {dataKeys.map((key) => (
              <Line
                key={key}
                dataKey={key}
                type="monotone"
                stroke={config[key]?.color || '#3b82f6'}
                strokeWidth={2}
                strokeOpacity={0.8}
                dot={false}
                connectNulls={false}
              />
            ))}
          </LineChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
