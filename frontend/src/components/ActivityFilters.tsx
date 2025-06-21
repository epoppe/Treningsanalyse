'use client';

import styled from 'styled-components';

const FiltersContainer = styled.div`
  margin-bottom: 2rem;
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
`;

const Select = styled.select`
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  min-width: 200px;
`;

const DateInput = styled.input`
  padding: 0.5rem;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
`;

interface ActivityFiltersProps {
  onFilterChange: (filters: {
    type: string;
    startDate: string;
    endDate: string;
  }) => void;
  activityTypes: string[];
}

export default function ActivityFilters({ onFilterChange, activityTypes }: ActivityFiltersProps) {
  const handleChange = (field: string, value: string) => {
    onFilterChange({
      type: field === 'type' ? value : 'all',
      startDate: field === 'startDate' ? value : '',
      endDate: field === 'endDate' ? value : '',
    });
  };

  return (
    <FiltersContainer>
      <Select
        onChange={(e) => handleChange('type', e.target.value)}
        defaultValue="all"
      >
        <option key="all" value="all">Alle aktiviteter</option>
        {activityTypes.map((type, index) => (
          <option key={`${type}-${index}`} value={type}>
            {type}
          </option>
        ))}
      </Select>

      <DateInput
        type="date"
        onChange={(e) => handleChange('startDate', e.target.value)}
        placeholder="Fra dato"
      />

      <DateInput
        type="date"
        onChange={(e) => handleChange('endDate', e.target.value)}
        placeholder="Til dato"
      />
    </FiltersContainer>
  );
} 