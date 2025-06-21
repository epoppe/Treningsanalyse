'use client';

import styled from 'styled-components';
import { Activity } from '../store/slices/activitiesSlice';
import { useRouter } from 'next/navigation';
import { useSelector } from 'react-redux';
import { RootState } from '@/store';

const ActivityContainer = styled.div`
  padding: 1rem;
`;

const ActivityCardWrapper = styled.div`
  width: 100%;
  margin-bottom: 1rem;
`;

const ActivityCard = styled.div`
  background: white;
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
`;

const ActivityTitle = styled.h3`
  margin: 0 0 0.5rem 0;
  color: #2c3e50;
`;

const ActivityDetails = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem;
  color: #666;
`;

const Stat = styled.div`
  display: flex;
  flex-direction: column;
  
  span:first-child {
    font-size: 0.875rem;
    color: #999;
  }
  
  span:last-child {
    font-size: 1.125rem;
    color: #2c3e50;
  }
`;

interface ActivityListProps {
  activities: Activity[];
}

const ActivityList = () => {
  const router = useRouter();
  const { items: activities, status } = useSelector((state: RootState) => state.activities);

  const handleActivityClick = (activityId: number) => {
    router.push(`/activities/${activityId}`);
  };

  if (status === 'loading') return <p>Laster aktiviteter...</p>;
  if (status === 'failed') return <p>Kunne ikke laste aktiviteter.</p>;

  if (!activities) {
    return <p>Venter på aktiviteter...</p>;
  }

  return (
    <ActivityContainer>
      {activities.map((activity) => (
        <ActivityCard 
          key={activity.id} 
          className="hover:shadow-lg transition-shadow cursor-pointer"
          onClick={() => handleActivityClick(activity.id)}
        >
          <ActivityTitle>{activity.name}</ActivityTitle>
          <ActivityDetails>
            {[
              {
                key: 'distance',
                label: 'Distanse',
                value: `${(activity.distance || 0).toFixed(2)} km`
              },
              {
                key: 'duration',
                label: 'Varighet',
                value: `${Math.round(activity.duration || 0)} min`
              },
              {
                key: 'calories',
                label: 'Kalorier',
                value: (activity.calories || 0).toString()
              },
              ...(activity.average_hr > 0 ? [{
                key: 'average_hr',
                label: 'Snitt puls',
                value: `${Math.round(activity.average_hr)} bpm`
              }] : []),
              ...(activity.vo2_max > 0 ? [{
                key: 'vo2_max',
                label: 'VO2 Max',
                value: Math.round(activity.vo2_max).toString()
              }] : [])
            ].map(stat => (
              <Stat key={stat.key}>
                <span>{stat.label}</span>
                <span>{stat.value}</span>
              </Stat>
            ))}
          </ActivityDetails>
        </ActivityCard>
      ))}
    </ActivityContainer>
  );
};

export default ActivityList; 