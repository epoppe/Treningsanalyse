'use client';

import React from 'react';
import { Button } from '@/components/ui/button';

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
  activityCount,
}) => {
  const timeFilters: Array<{ label: string; value: '12months' | '3months' }> = [
    { label: 'Se 3 måneder', value: '3months' },
    { label: 'Se 12 måneder', value: '12months' },
  ];

  return (
    <div
      style={{
        display: 'flex',
        width: '100%',
        boxSizing: 'border-box',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'nowrap',
        border: '1px solid rgba(226, 232, 240, 0.9)',
        borderRadius: '18px',
        background: '#f8fafc',
        padding: '0.75rem 1rem',
        boxShadow: '0 4px 14px rgba(15, 23, 42, 0.05)',
      }}
    >
      <div className="flex flex-nowrap items-center gap-2">
        {timeFilters.map((filter) => {
          const isActive = currentTimeFilter === filter.value;
          return (
            <Button
              key={filter.value}
              type="button"
              variant={isActive ? 'default' : 'secondary'}
              size="sm"
              disabled={isRefreshing}
              onClick={() => onTimeFilterChange?.(filter.value)}
              style={{
                minWidth: '9rem',
                display: 'inline-flex',
                justifyContent: 'center',
                padding: '0.45rem 1rem',
                borderRadius: '9999px',
                border: '1px solid rgba(148, 163, 184, 0.4)',
                backgroundColor: isActive ? '#2563eb' : '#e2e8f0',
                color: isActive ? '#f8fafc' : '#1e293b',
                cursor: isRefreshing ? 'not-allowed' : 'pointer',
              }}
            >
              {filter.label}
            </Button>
          );
        })}
        {onRefreshActivities && (
          <Button
            type="button"
            variant={currentTimeFilter === 'all' ? 'default' : 'outline'}
            size="sm"
            disabled={isRefreshing}
            onClick={() => {
              onRefreshActivities();
              onTimeFilterChange?.('all');
            }}
            className="min-w-[7rem] justify-center text-sm"
            style={{
              minWidth: '7rem',
              display: 'inline-flex',
              justifyContent: 'center',
              padding: '0.45rem 1rem',
              borderRadius: '9999px',
              border: '1px solid rgba(148, 163, 184, 0.4)',
              backgroundColor: currentTimeFilter === 'all' ? '#2563eb' : '#f8fafc',
              color: currentTimeFilter === 'all' ? '#f8fafc' : '#1e293b',
              cursor: isRefreshing ? 'not-allowed' : 'pointer',
            }}
          >
            {isRefreshing ? 'Laster...' : 'Se alle'}
          </Button>
        )}
      </div>

      {activityCount && (
        <span
          className="whitespace-nowrap text-sm font-semibold"
          style={{ fontSize: '0.875rem', color: '#1e293b' }}
        >
          {activityCount}
        </span>
      )}
    </div>
  );
};

export default ActivityViewControls; 