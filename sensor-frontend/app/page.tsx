// app/page.tsx
'use client'

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'
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

// Alarm definitions
const ALARM_RANGES = {
  tank_temperature: { min: 30, max: 40 },
  ph: { min: 6, max: 8 }
}

// Helper function for alarm status
function getAlarmStatus(value: number | null, range: { min: number, max: number }) {
  if (value === null || value === undefined) return 'unknown'
  if (value >= range.min && value <= range.max) return 'safe'
  return 'critical'
}

// Helper function for tank temperature alarm (takes maximum of temp1 and temp2)
function getTankTemperatureAlarm(temp1: number | null, temp2: number | null) {
  const temps = [temp1, temp2].filter(t => t !== null) as number[]
  if (temps.length === 0) return 'unknown'
  const maxTemp = Math.max(...temps)
  return getAlarmStatus(maxTemp, ALARM_RANGES.tank_temperature)
}

export default function Home() {
  const [data, setData] = useState<SensorData | null>(null)
  const [loading, setLoading] = useState(true)

  // Helper to fetch the latest entry
  const fetchLatest = async () => {
    setLoading(true)
    const { data: rows } = await supabase
      .from('sensor_data')
      .select('*')
      .order('timestamp', { ascending: false })
      .limit(1)
    setData(rows?.[0] ?? null)
    setLoading(false)
  }

  // Subscribe to changes in real-time
  useEffect(() => {
    fetchLatest()
    const sub = supabase
      .channel('sensor_data_realtime')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'sensor_data' },
        payload => {
          setData(payload.new as SensorData)
        }
      )
      .subscribe()

    // Polling fallback for robustness
    const poll = setInterval(fetchLatest, 12000)

    return () => {
      sub.unsubscribe()
      clearInterval(poll)
    }
  }, [])

  if (loading && !data) {
    return (
      <main className="flex items-center justify-center min-h-screen bg-gray-50">
        <div className="text-gray-500 text-lg">Loading latest data…</div>
      </main>
    )
  }

  const tankTemperatureAlarm = getTankTemperatureAlarm(data?.temp1 ?? null, data?.temp2 ?? null)
  const phAlarm = getAlarmStatus(data?.ph ?? null, ALARM_RANGES.ph)

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp)
    // No timezone correction needed - time is already correct
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    })
  }

  return (
    <main className="min-h-screen bg-gray-50 p-4 flex justify-center">
      <div className="container mx-auto max-w-4xl">
        <div className="bg-white rounded-2xl shadow-xl border border-gray-100 overflow-hidden">
          {/* Header */}
          <div className="bg-gradient-to-r from-green-500 to-green-500 text-white p-4 md:p-6">
            <div className="flex justify-between items-center mb-2">
              <h1 className="text-xl md:text-2xl font-bold">
                Current Sensor Data
              </h1>
              <Link 
                href="/charts" 
                className="bg-green-500 hover:bg-green-400 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition-colors duration-200"
              >
                📊 Charts
              </Link>
            </div>
            <p className="text-green-100 text-sm">
              Smart Biodigester Monitoring System
            </p>
          </div>
          
          <div className="p-4 md:p-6 space-y-4 md:space-y-6">
            {/* Critical Alerts */}
            {(tankTemperatureAlarm === 'critical' || phAlarm === 'critical') && (
              <div className="bg-red-50 border-l-4 border-red-400 rounded-lg p-4">
                <div className="flex items-start">
                  <div className="flex-shrink-0">
                    <span className="text-red-400 text-xl">⚠️</span>
                  </div>
                  <div className="ml-3">
                    <h3 className="text-sm font-medium text-red-800">Critical Values Detected!</h3>
                    <div className="mt-2 text-sm text-red-700">
                      <ul className="list-disc list-inside space-y-1">
                        {tankTemperatureAlarm === 'critical' && (
                          <li>Tank temperature outside optimal range (30-40°C)</li>
                        )}
                        {phAlarm === 'critical' && (
                          <li>pH value outside optimal range (6-8)</li>
                        )}
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            )}
            
            {/* Sensor Values Grid */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 md:gap-4">
              <LabelVal label="Timestamp" value={formatTimestamp(data?.timestamp ?? '')} />
              <LabelVal label="pH Value" value={format(data?.ph)} alarm={phAlarm} />
              <LabelVal label="pH Voltage [mV]" value={format(data?.ph_voltage)} />
              <LabelVal label="Temp. 1 [°C]" value={format(data?.temp1)} alarm={tankTemperatureAlarm} />
              <LabelVal label="Temp. 2 [°C]" value={format(data?.temp2)} alarm={tankTemperatureAlarm} />
              <LabelVal label="BME Temp. [°C]" value={format(data?.bme_temperature)} />
              <LabelVal label="BME Humidity [%]" value={format(data?.bme_humidity)} />
              <LabelVal label="BME Pressure [hPa]" value={format(data?.bme_pressure)} />
              <LabelVal label="BME Gas Resistance [kΩ]" value={format(data?.bme_gas_resistance)} />
              <LabelVal label="Methane [ppm]" value={format(data?.methane_ppm)} />
              <LabelVal label="Methane [%]" value={format(data?.methane_percent)} />
              <LabelVal label="Methane Temp. [°C]" value={format(data?.methane_temperature)} />
            </div>
            
            {/* Raw Data Sections */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <h2 className="font-semibold text-base mb-2 text-gray-800">Methane Raw Output</h2>
                <div className="font-mono bg-gray-100 rounded-lg p-3 text-xs break-all border">
                  {data?.methan_raw && data.methan_raw.length > 0
                    ? data.methan_raw.join(', ')
                    : '–'}
                </div>
              </div>
              
              <div>
                <h2 className="font-semibold text-base mb-2 text-gray-800">Methane Errors</h2>
                <div className="bg-gray-100 rounded-lg p-3 border min-h-[60px]">
                  <ul className="text-xs text-red-700 space-y-1">
                    {Array.isArray(data?.methane_faults) && data.methane_faults.length > 0
                      ? data.methane_faults.map((f, i) => <li key={i}>• {f}</li>)
                      : <li className="text-gray-500">No errors</li>}
                  </ul>
                </div>
              </div>
            </div>
            
            {/* System Status */}
            <div className="bg-gray-50 rounded-lg p-4 border">
              <h2 className="font-semibold text-base mb-3 text-gray-800">System Status</h2>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div className="flex justify-between items-center p-2 bg-white rounded border">
                  <span className="text-sm font-medium">Tank Temperature:</span>
                  <span className={`text-sm font-bold ${
                    tankTemperatureAlarm === 'critical' ? 'text-red-600' : 
                    tankTemperatureAlarm === 'safe' ? 'text-green-600' : 'text-gray-500'
                  }`}>
                    {tankTemperatureAlarm === 'critical' ? '⚠️ Critical' : 
                     tankTemperatureAlarm === 'safe' ? '✅ Optimal' : '❓ Unknown'}
                  </span>
                </div>
                <div className="flex justify-between items-center p-2 bg-white rounded border">
                  <span className="text-sm font-medium">pH Value:</span>
                  <span className={`text-sm font-bold ${
                    phAlarm === 'critical' ? 'text-red-600' : 
                    phAlarm === 'safe' ? 'text-green-600' : 'text-gray-500'
                  }`}>
                    {phAlarm === 'critical' ? '⚠️ Critical' : 
                     phAlarm === 'safe' ? '✅ Optimal' : '❓ Unknown'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  )
}

function format(val: number | string | null | undefined) {
  if (val === null || val === undefined || Number.isNaN(val)) return '–'
  if (typeof val === 'number') return val.toFixed(2)
  return val
}

function LabelVal({ label, value, alarm }: { label: string, value: string | number, alarm?: string }) {
  return (
    <div className="bg-white p-3 rounded-lg border border-gray-200 shadow-sm">
      <span className="block text-xs font-medium text-gray-600 mb-1">{label}</span>
      <span className={`font-mono text-sm font-semibold ${
        alarm === 'critical' ? 'text-red-600' : 
        alarm === 'safe' ? 'text-green-600' : 'text-gray-900'
      }`}>
        {value}
      </span>
    </div>
  )
}
