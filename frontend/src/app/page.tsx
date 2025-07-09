'use client';

import { useState, useEffect, useMemo } from 'react';
import styled from 'styled-components';
import { useAppDispatch, useAppSelector } from '../store/hooks';
import { fetchActivities, Activity } from '../store/slices/activitiesSlice';
import ActivityList from '../components/ActivityList';
import ActivityChart from '../components/ActivityChart';
import DataSyncPanel from '../components/DataSyncPanel';
import RunningEconomyTable from '../components/RunningEconomyTable';

const MainContainer = styled.div`
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
`;

const Title = styled.h1`
  font-size: 2.5rem;
  color: #333;
  margin-bottom: 2rem;
`;

const Header = styled.header`
  margin-bottom: 2rem;
  text-align: center;
`;

const Subtitle = styled.p`
  color: #666;
  font-size: 1.125rem;
`;

const FiltersContainer = styled.div`
  margin-bottom: 2rem;
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  justify-content: center;
  align-items: flex-start;
`;

const FilterSection = styled.div`
  background: white;
  padding: 1rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  min-width: 300px;
`;

const FilterTitle = styled.h3`
  margin: 0 0 0.5rem 0;
  color: #2c3e50;
  font-size: 1rem;
`;

const CheckboxContainer = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-bottom: 1rem;
`;

const CheckboxLabel = styled.label`
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  transition: background-color 0.2s;
  
  &:hover {
    background-color: #f8f9fa;
  }
`;

const Checkbox = styled.input`
  cursor: pointer;
`;

const CheckboxText = styled.span`
  font-size: 0.9rem;
  color: #333;
`;

const SelectAllButton = styled.button`
  padding: 0.25rem 0.5rem;
  background: #3498db;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;
  margin-right: 0.5rem;

  &:hover {
    background: #2980b9;
  }
`;

const ClearAllButton = styled.button`
  padding: 0.25rem 0.5rem;
  background: #e74c3c;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.8rem;

  &:hover {
    background: #c0392b;
  }
`;

const SelectedTypesDisplay = styled.div`
  margin-top: 0.5rem;
  padding: 0.5rem;
  background: #f8f9fa;
  border-radius: 4px;
  font-size: 0.9rem;
  color: #666;
  min-height: 1.5rem;
`;

const DateFiltersSection = styled.div`
  background: white;
  padding: 1rem;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  min-width: 300px;
`;

const DateInputsContainer = styled.div`
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
`;

const DateInput = styled.input`
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  flex: 1;
  min-width: 120px;
`;

export default function Home() {
  const dispatch = useAppDispatch();
  const { items: activities, status, error } = useAppSelector((state) => state.activities);
  const [filteredActivities, setFilteredActivities] = useState<Activity[]>([]);
  const [selectedActivityTypes, setSelectedActivityTypes] = useState<string[]>([]);
  const [startDate, setStartDate] = useState<string>('');
  const [endDate, setEndDate] = useState<string>('');

  const getReadableActivityTypeName = (typeKey: string): string => {
    const nameMap: { [key: string]: string } = {
      'running': 'Løping',
      'treadmill_running': 'Tredemølle løping',
      'cycling': 'Sykling',
      'resort_skiing': 'Alpin',
      'cross_country_skiing_ws': 'Langrenn',
      'indoor_cardio': 'Innendørs cardio',
      'walking': 'Gåing',
      'hiking': 'Fotturer',
      'mountain_biking': 'Terrengsykling',
      'resort_skiing_snowboarding_ws': 'Alpint/Snowboard',
      'other': 'Annet',
      'trail_running': 'Terrengløp',
      'gravel_cycling': 'Grussykling',
      'lap_swimming': 'Svømming',
      'multi_sport': 'Flerbruk',
      'open_water_swimming': 'Åpent vann svømming',
      'indoor_cycling': 'Innendørs sykling',
      'swimming': 'Svømming',
      'road_biking': 'Landeveissykling',
      'street_running': 'Gateløp',
      'bikeToRunTransition_v2': 'Sykkel-til-løp overgang'
    };
    
    return nameMap[typeKey] || typeKey;
  };

  const activityTypes = useMemo(() => {
    const typeMap = new Map<string, string>();
    
    activities.forEach(activity => {
      const typeKey = activity.activityType?.typeKey;
      if (typeKey) {
        // Mapper til mer lesbare navn
        const readableName = getReadableActivityTypeName(typeKey);
        typeMap.set(typeKey, readableName);
      }
    });
    
    return Array.from(typeMap.entries()).sort((a, b) => a[1].localeCompare(b[1]));
  }, [activities]);

  useEffect(() => {
    if (status === 'idle') {
      dispatch(fetchActivities());
    }
  }, [status, dispatch]);

  useEffect(() => {
    // Sett alle aktivitetstyper som valgt når aktiviteter lastes første gang
    if (activities.length > 0 && selectedActivityTypes.length === 0) {
      const allTypes = activityTypes.map(([typeKey]) => typeKey);
      setSelectedActivityTypes(allTypes);
    }
  }, [activities, selectedActivityTypes.length, activityTypes]);

  useEffect(() => {
    let tempActivities = [...activities];

    // Filtrer på aktivitetstyper
    if (selectedActivityTypes.length > 0) {
      tempActivities = tempActivities.filter(activity => 
        selectedActivityTypes.includes(activity.activityType?.typeKey || '')
      );
    }

    // Filtrer på startdato
    if (startDate) {
      tempActivities = tempActivities.filter(activity => 
        new Date(activity.startTimeLocal) >= new Date(startDate)
      );
    }

    // Filtrer på sluttdato
    if (endDate) {
      const endDateTime = new Date(endDate);
      endDateTime.setDate(endDateTime.getDate() + 1);
      tempActivities = tempActivities.filter(activity => 
        new Date(activity.startTimeLocal) < endDateTime
      );
    }

    setFilteredActivities(tempActivities);
  }, [activities, selectedActivityTypes, startDate, endDate]);

  const handleActivityTypeChange = (typeKey: string, checked: boolean) => {
    if (checked) {
      setSelectedActivityTypes(prev => [...prev, typeKey]);
    } else {
      setSelectedActivityTypes(prev => prev.filter(t => t !== typeKey));
    }
  };

  const handleSelectAll = () => {
    const allTypes = activityTypes.map(([typeKey]) => typeKey);
    setSelectedActivityTypes(allTypes);
  };

  const handleClearAll = () => {
    setSelectedActivityTypes([]);
  };

  if (status === 'loading') {
    return <div>Laster aktiviteter...</div>;
  }

  if (status === 'failed') {
    return <div>Error: {error}</div>;
  }

  return (
    <MainContainer>
      <Title>Treningsdagbok</Title>
      <DataSyncPanel />
      
      <FiltersContainer>
        <FilterSection>
          <FilterTitle>Velg aktivitetstyper</FilterTitle>
          <div>
            <SelectAllButton onClick={handleSelectAll}>Velg alle</SelectAllButton>
            <ClearAllButton onClick={handleClearAll}>Fjern alle</ClearAllButton>
          </div>
          <CheckboxContainer>
            {activityTypes.map(([typeKey, readableName]) => (
              <CheckboxLabel key={typeKey}>
                <Checkbox
                  type="checkbox"
                  checked={selectedActivityTypes.includes(typeKey)}
                  onChange={(e) => handleActivityTypeChange(typeKey, e.target.checked)}
                />
                <CheckboxText>{readableName}</CheckboxText>
              </CheckboxLabel>
            ))}
          </CheckboxContainer>
          <SelectedTypesDisplay>
            Valgte typer: {selectedActivityTypes.length === 0 
              ? 'Ingen valgt' 
              : selectedActivityTypes.map(typeKey => {
                  const typePair = activityTypes.find(([key]) => key === typeKey);
                  return typePair ? typePair[1] : typeKey;
                }).join(', ')
            }
          </SelectedTypesDisplay>
        </FilterSection>

        <DateFiltersSection>
          <FilterTitle>Datofilter</FilterTitle>
          <DateInputsContainer>
            <DateInput
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              placeholder="Fra dato"
            />
            <DateInput
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              placeholder="Til dato"
            />
          </DateInputsContainer>
        </DateFiltersSection>
      </FiltersContainer>

      <ActivityChart activities={filteredActivities} metric="distance" title="Distanse over tid" />
      <RunningEconomyTable activities={filteredActivities} />
      <ActivityList activities={filteredActivities} />
    </MainContainer>
  );
}
