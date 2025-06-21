'use client';

import styled from 'styled-components';
import { Activity } from '../store/slices/activitiesSlice';

const TableContainer = styled.div`
  margin-top: 2rem;
  background: white;
  border-radius: 8px;
  padding: 1.5rem;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
`;

const TableTitle = styled.h2`
  font-size: 1.5rem;
  color: #2c3e50;
  margin-bottom: 1rem;
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
    .filter(a => a.activityType?.typeKey === 'running' && a.averageSpeed && a.averageHR)
    .map(activity => {
      const averageSpeedKmh = activity.averageSpeed * 3.6;
      const runningEconomy = activity.averageHR > 0 
        ? (averageSpeedKmh / activity.averageHR) * 100 
        : 0;
      
      return {
        ...activity,
        averageSpeedKmh,
        runningEconomy
      };
    })
    .sort((a, b) => new Date(b.start_time).getTime() - new Date(a.start_time).getTime());

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
            <tr key={activity.id}>
              <td>{new Date(activity.start_time).toLocaleDateString('nb-NO')}</td>
              <td>{activity.name}</td>
              <td>{activity.averageSpeedKmh.toFixed(2)}</td>
              <td>{Math.round(activity.averageHR)}</td>
              <td>{activity.runningEconomy.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </StyledTable>
    </TableContainer>
  );
};

export default RunningEconomyTable; 