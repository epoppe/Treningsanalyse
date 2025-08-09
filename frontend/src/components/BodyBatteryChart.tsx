import React from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend
} from 'recharts';
import { format, parseISO } from 'date-fns';
import { nb } from 'date-fns/locale';

interface BodyBatteryData {
  date: string;
  max_body_battery: number | null;
  min_body_battery: number | null;
  body_battery_charged: number | null;
  body_battery_drained: number | null;
  body_battery_charged_start: number | null;
  body_battery_drained_start: number | null;
  net_charge: number | null;
}

interface BodyBatteryChartProps {
  data: BodyBatteryData[];
  title: string;
}

const CustomAxisTick = ({ x, y, payload }: any) => (
  <g transform={`translate(${x},${y})`}>
    <text x={0} y={0} dy={16} textAnchor="middle" fill="#666" fontSize={12}>
      {format(parseISO(payload.value), 'dd.MM', { locale: nb })}
    </text>
  </g>
);

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const date = format(parseISO(label), 'EEEE, dd. MMMM yyyy', { locale: nb });
    
    return (
      <div style={{
        backgroundColor: 'white',
        border: '1px solid #ccc',
        borderRadius: '4px',
        padding: '10px',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
      }}>
        <p style={{ margin: '0 0 8px 0', fontWeight: 'bold' }}>{date}</p>
        {payload.map((entry: any, index: number) => (
          <p key={index} style={{ 
            margin: '4px 0', 
            color: entry.color,
            fontSize: '14px'
          }}>
            {entry.name}: {entry.value !== null ? `${entry.value}%` : 'Ingen data'}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

const BodyBatteryChart: React.FC<BodyBatteryChartProps> = ({ data, title }) => {
  // Filtrer ut dager uten data
  const filteredData = data.filter(item => 
    item.max_body_battery !== null || 
    item.min_body_battery !== null ||
    item.body_battery_charged_start !== null ||
    item.body_battery_drained_start !== null
  );

  if (filteredData.length === 0) {
    return (
      <div style={{
        background: 'white',
        borderRadius: '8px',
        padding: '2rem',
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
        textAlign: 'center',
        color: '#666'
      }}>
        <h3>{title}</h3>
        <p>Ingen Body Battery-data tilgjengelig for valgt periode</p>
      </div>
    );
  }

  return (
    <div style={{
      background: 'white',
      borderRadius: '8px',
      padding: '1.5rem',
      boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
      marginBottom: '2rem'
    }}>
      <h3 style={{ margin: '0 0 1rem 0', color: '#2c3e50' }}>{title}</h3>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={filteredData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis 
            dataKey="date" 
            tick={<CustomAxisTick />}
            interval="preserveStartEnd"
          />
          <YAxis 
            domain={[0, 100]}
            tickFormatter={(value) => `${value}%`}
            stroke="#666"
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend />
          
          {/* Høyeste Body Battery */}
          <Line
            type="monotone"
            dataKey="max_body_battery"
            stroke="#27ae60"
            strokeWidth={2}
            dot={{ fill: '#27ae60', strokeWidth: 2, r: 4 }}
            activeDot={{ r: 6 }}
            name="Høyeste Body Battery"
            connectNulls={false}
          />
          
          {/* Laveste Body Battery */}
          <Line
            type="monotone"
            dataKey="min_body_battery"
            stroke="#e74c3c"
            strokeWidth={2}
            dot={{ fill: '#e74c3c', strokeWidth: 2, r: 4 }}
            activeDot={{ r: 6 }}
            name="Laveste Body Battery"
            connectNulls={false}
          />
          
          {/* Start oppladet */}
          <Line
            type="monotone"
            dataKey="body_battery_charged_start"
            stroke="#3498db"
            strokeWidth={2}
            dot={{ fill: '#3498db', strokeWidth: 2, r: 4 }}
            activeDot={{ r: 6 }}
            name="Start (Oppladet)"
            connectNulls={false}
          />
          
          {/* Start utladet */}
          <Line
            type="monotone"
            dataKey="body_battery_drained_start"
            stroke="#f39c12"
            strokeWidth={2}
            dot={{ fill: '#f39c12', strokeWidth: 2, r: 4 }}
            activeDot={{ r: 6 }}
            name="Start (Utladet)"
            connectNulls={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
};

export default BodyBatteryChart; 