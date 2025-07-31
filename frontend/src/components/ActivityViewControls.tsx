'use client';

import React from 'react';
import styled from 'styled-components';

const ViewControlsContainer = styled.div`
  display: flex;
  gap: 1rem;
  margin-bottom: 1rem;
  justify-content: center;
  align-items: center;
  flex-wrap: wrap;
`;

const TimeFilterButton = styled.button<{ $active: boolean }>`
  background-color: ${props => props.$active ? '#007bff' : '#6c757d'};
  color: white;
  border: none;
  padding: 8px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;

  &:hover {
    background-color: ${props => props.$active ? '#0056b3' : '#5a6268'};
  }

  &:disabled {
    background-color: #555;
    cursor: not-allowed;
  }
`;

const RefreshActivitiesButton = styled.button`
  background-color: #007bff;
  color: white;
  border: none;
  padding: 8px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;

  &:hover {
    background-color: #0056b3;
  }

  &:disabled {
    background-color: #555;
    cursor: not-allowed;
  }
`;

const ActivityCount = styled.div`
  color: #666;
  font-size: 14px;
  white-space: nowrap;
  margin-left: auto;
`;

interface ActivityViewControlsProps {
  onTimeFilterChange?: (filter: 'all' | '12months' | '3months') => void;
  currentTimeFilter?: 'all' | '12months' | '3months';
  onRefreshActivities?: () => void;
  isRefreshing?: boolean;
  activityCount?: string;
}

const ActivityViewControls: React.FC<ActivityViewControlsProps> = ({ 
  onTimeFilterChange, 
  currentTimeFilter = 'all',
  onRefreshActivities,
  isRefreshing = false,
  activityCount
}) => {
  return (
    <ViewControlsContainer>
      {onTimeFilterChange && (
        <>
          <TimeFilterButton 
            $active={currentTimeFilter === '12months'}
            onClick={() => onTimeFilterChange('12months')}
            disabled={isRefreshing}
          >
            Se 12 måneder
          </TimeFilterButton>
          <TimeFilterButton 
            $active={currentTimeFilter === '3months'}
            onClick={() => onTimeFilterChange('3months')}
            disabled={isRefreshing}
          >
            Se 3 måneder
          </TimeFilterButton>
        </>
      )}
      
      {onRefreshActivities && (
        <RefreshActivitiesButton 
          onClick={onRefreshActivities}
          disabled={isRefreshing}
        >
          {isRefreshing ? 'Laster...' : 'Se alle'}
        </RefreshActivitiesButton>
      )}
      
      {activityCount && (
        <ActivityCount>
          {activityCount}
        </ActivityCount>
      )}
    </ViewControlsContainer>
  );
};

export default ActivityViewControls; 