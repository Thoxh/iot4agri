// app/page.tsx
'use client'

import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'

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
      <main className="flex items-center justify-center min-h-screen">
        <div className="text-gray-500 text-lg">Loading latest data…</div>
      </main>
    )
  }

  return (
    <main className="flex items-center justify-center min-h-screen bg-gray-50">
      <div className="rounded-2xl shadow-2xl bg-white max-w-2xl w-full p-8 space-y-4 border border-gray-100">
        <h1 className="text-2xl font-bold text-center mb-4">
          Aktuelle Sensordaten
        </h1>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <LabelVal label="Zeitstempel" value={data?.timestamp ?? '–'} />
          <LabelVal label="pH" value={format(data?.ph)} />
          <LabelVal label="pH-Spannung [mV]" value={format(data?.ph_voltage)} />
          <LabelVal label="Temp. 1 [°C]" value={format(data?.temp1)} />
          <LabelVal label="Temp. 2 [°C]" value={format(data?.temp2)} />
          <LabelVal label="BME Temp. [°C]" value={format(data?.bme_temperature)} />
          <LabelVal label="BME Feuchte [%]" value={format(data?.bme_humidity)} />
          <LabelVal label="BME Druck [hPa]" value={format(data?.bme_pressure)} />
          <LabelVal label="BME Gaswiderstand [kΩ]" value={format(data?.bme_gas_resistance)} />
          <LabelVal label="Methan [ppm]" value={format(data?.methane_ppm)} />
          <LabelVal label="Methan [%]" value={format(data?.methane_percent)} />
          <LabelVal label="Methan Temp. [°C]" value={format(data?.methane_temperature)} />
        </div>
        <div className="mt-4">
          <h2 className="font-semibold text-base mb-1">Methan RAW Output</h2>
          <div className="font-mono bg-gray-100 rounded p-2 text-xs break-all">
            {data?.methan_raw && data.methan_raw.length > 0
              ? data.methan_raw.join(', ')
              : '–'}
          </div>
        </div>
        <div className="mt-4">
          <h2 className="font-semibold text-base mb-1">Methan Fehler</h2>
          <ul className="list-disc ml-4 text-xs text-red-700">
            {Array.isArray(data?.methane_faults) && data.methane_faults.length > 0
              ? data.methane_faults.map((f, i) => <li key={i}>{f}</li>)
              : <li>–</li>}
          </ul>
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

function LabelVal({ label, value }: { label: string, value: string | number }) {
  return (
    <div>
      <span className="block text-gray-500">{label}</span>
      <span className="font-mono text-base text-green-600">{value}</span>
    </div>
  )
}
