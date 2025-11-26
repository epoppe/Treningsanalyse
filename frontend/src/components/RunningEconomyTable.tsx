'use client';

import styled from 'styled-components';
import { Activity } from '../types';

const TableContainer = styled.div`
  margin-top: 0.5rem;
  margin-bottom: 0.1rem;
  background: white;
  border-radius: 8px;
  padding: 1rem;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
`;

const TableTitle = styled.h2`
  font-size: 1.5rem;
  color: #2c3e50;
  margin-bottom: 0.5rem;
`;

const StyledTable = styled.table`
  width: 100%;
  border-collapse: collapse;
  
  th, td {
    padding: 0.75rem 1rem;
    text-align: left;
    border-bottom: 1px solid #e0e0e0;
  }

  th {
    font-size: 0.875rem;
    color: #666;
    text-transform: uppercase;
  }

  tbody tr:hover {
    background-color: #f9f9f9;
  }
`;

interface RunningEconomyTableProps {
  activities: Activity[];
}

const RunningEconomyTable = ({ activities }: RunningEconomyTableProps) => {
  const runningActivities = activities
    .filter(a => {
      const typeKey = a.activityType?.typeKey?.toLowerCase();
      return typeKey?.includes('running') && typeKey !== 'treadmill_running';
    })
    .map(activity => {
      if (activity.averageSpeed && activity.averageSpeed > 0 && activity.averageHR && activity.averageHR > 0) {
        const averageSpeedKmh = activity.averageSpeed * 3.6;
        const runningEconomy = (averageSpeedKmh / activity.averageHR) * 100;
        
        return {
          ...activity,
          averageSpeedKmh,
          runningEconomy
        };
      }
      return {
        ...activity,
        averageSpeedKmh: 0,
        runningEconomy: 0
      };
    })
    .filter(a => a.runningEconomy > 0)
    .sort((a, b) => new Date(b.startTimeLocal).getTime() - new Date(a.startTimeLocal).getTime());

  if (runningActivities.length === 0) {
    return null;
  }

  return (
    <TableContainer>
      <TableTitle>Analyse av Løpsøkonomi</TableTitle>
      <StyledTable>
        <thead>
          <tr>
            <th>Dato</th>
            <th>Aktivitet</th>
            <th>Snittfart (km/t)</th>
            <th>Snittpuls (slag/min)</th>
            <th>Løpsøkonomi</th>
          </tr>
        </thead>
        <tbody>
          {runningActivities.map(activity => (
            <tr key={activity.activityId}>
              <td>{new Date(activity.startTimeLocal).toLocaleDateString('nb-NO')}</td>
              <td>{activity.activityName}</td>
              <td>{activity.averageSpeedKmh.toFixed(2)}</td>
              <td>{Math.round(activity.averageHR!)}</td>
              <td>{activity.runningEconomy.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </StyledTable>
    </TableContainer>
  );
};

export default RunningEconomyTable;