import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { activitiesApi, errorHandler } from '../../utils/api';
import { PayloadAction } from '@reduxjs/toolkit';

// Definer typer
export interface Activity {
  activityId: string;
  activityName?: string;
  activityType: {
    typeKey: string;
    parentTypeKey?: string;
  };
  averageHR?: number;
  averagePace?: number;
  averageRunningCadenceInStepsPerMinute?: number;
  averageSpeed?: number;
  avgStrideLength?: number;
  calories?: number;
  distance?: number;
  duration?: number;
  startTimeLocal: string;
  vO2MaxValue?: number;
  details?: { [key: string]: any };
}

interface ActivitiesState {
  items: Activity[];
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
  lastSync: string | null;
}

// Initial state
const initialState: ActivitiesState = {
  items: [],
  status: 'idle',
  error: null,
  lastSync: null
};

// Async thunks
export const fetchActivities = createAsyncThunk<Activity[], void, { rejectValue: string }>(
  'activities/fetchActivities',
  async (_, { rejectWithValue }) => {
    try {
      const response = await activitiesApi.getActivities();
      // Backend sender nå en flat liste, så vi returnerer den direkte.
      return response;
    } catch (error) {
      const errorInfo = errorHandler(error);
      return rejectWithValue(errorInfo.error);
    }
  }
);

export const fetchActivitiesByDateRange = createAsyncThunk(
  'activities/fetchActivitiesByDateRange',
  async ({ startDate, endDate, forceRefresh = false }: { 
    startDate: string; 
    endDate: string; 
    forceRefresh?: boolean;
  }, { rejectWithValue }) => {
    try {
      const response = await activitiesApi.getActivitiesByDateRange(startDate, endDate, forceRefresh);
      return response.activities || [];
    } catch (error) {
      const errorInfo = errorHandler(error);
      return rejectWithValue(errorInfo.error);
    }
  }
);

export const syncHistoricalData = createAsyncThunk(
  'activities/syncHistoricalData',
  async (startYear: number, { rejectWithValue }) => {
    try {
      const response = await activitiesApi.syncHistoricalData(startYear);
      return response;
    } catch (error) {
      const errorInfo = errorHandler(error);
      return rejectWithValue(errorInfo.error);
    }
  }
);

// Slice
const activitiesSlice = createSlice({
  name: 'activities',
  initialState,
  reducers: {
    clearError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      // fetchActivities
      .addCase(fetchActivities.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(fetchActivities.fulfilled, (state, action: PayloadAction<Activity[]>) => {
        state.status = 'succeeded';
        state.items = action.payload;
        state.lastSync = new Date().toISOString();
      })
      .addCase(fetchActivities.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload as string || 'Kunne ikke hente aktiviteter';
      })
      // fetchActivitiesByDateRange
      .addCase(fetchActivitiesByDateRange.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(fetchActivitiesByDateRange.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.items = action.payload;
      })
      .addCase(fetchActivitiesByDateRange.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload as string || 'Kunne ikke hente aktiviteter for perioden';
      })
      // syncHistoricalData
      .addCase(syncHistoricalData.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(syncHistoricalData.fulfilled, (state) => {
        state.status = 'succeeded';
        state.lastSync = new Date().toISOString();
      })
      .addCase(syncHistoricalData.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload as string || 'Kunne ikke synkronisere historiske data';
      });
  },
});

export const { clearError } = activitiesSlice.actions;

// Selectors
export const selectAllActivities = (state: { activities: ActivitiesState }) => state.activities.items;
export const selectActivitiesStatus = (state: { activities: ActivitiesState }) => state.activities.status;
export const selectActivitiesError = (state: { activities: ActivitiesState }) => state.activities.error;

export default activitiesSlice.reducer; 