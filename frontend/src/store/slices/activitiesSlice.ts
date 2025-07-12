import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { activitiesApi, errorHandler } from '../../utils/api';
import { Activity } from '../../types';

// Definer typer - fjernet herfra, importeres nå fra types/index.ts

interface ActivitiesState {
  items: Activity[];
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
  lastSync: string | null;
  totalCount: number | null;
  loadedCount: number;
}

// Initial state
const initialState: ActivitiesState = {
  items: [],
  status: 'idle',
  error: null,
  lastSync: null,
  totalCount: null,
  loadedCount: 0
};

// Async thunks
export const fetchActivities = createAsyncThunk<Activity[], { forceRefresh?: boolean; limit?: number }, { rejectValue: string }>(
  'activities/fetchActivities',
  async ({ forceRefresh = false, limit = 100 } = {}, { rejectWithValue }) => {
    try {
      console.log('[fetchActivities] Starter API-kall...');
      const response = await activitiesApi.getActivities(forceRefresh, limit);
      console.log('[fetchActivities] Hentet response:', response?.length || 0, 'aktiviteter');
      // Backend sender nå en flat liste, så vi returnerer den direkte.
      return response;
    } catch (error) {
      console.error('[fetchActivities] Feil ved henting av aktiviteter:', error);
      const errorInfo = errorHandler(error);
      return rejectWithValue(errorInfo.error);
    }
  }
);

export const fetchMoreActivities = createAsyncThunk<Activity[], { forceRefresh?: boolean; limit?: number; offset?: number }, { rejectValue: string }>(
  'activities/fetchMoreActivities',
  async ({ forceRefresh = false, limit = 500, offset = 0 } = {}, { rejectWithValue }) => {
    try {
      console.log('[fetchMoreActivities] Starter API-kall...');
      const response = await activitiesApi.getMoreActivities(forceRefresh, limit, offset);
      console.log('[fetchMoreActivities] Hentet response:', response?.length || 0, 'aktiviteter');
      return response;
    } catch (error) {
      console.error('[fetchMoreActivities] Feil ved henting av flere aktiviteter:', error);
      const errorInfo = errorHandler(error);
      return rejectWithValue(errorInfo.error);
    }
  }
);

export const fetchActivityCount = createAsyncThunk<number, void, { rejectValue: string }>(
  'activities/fetchActivityCount',
  async (_, { rejectWithValue }) => {
    try {
      console.log('[fetchActivityCount] Starter API-kall...');
      const count = await activitiesApi.getActivityCount();
      console.log('[fetchActivityCount] Hentet antall aktiviteter:', count);
      return count;
    } catch (error) {
      console.error('[fetchActivityCount] Feil ved henting av aktivitetsantall:', error);
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

export const fetchAllActivities = createAsyncThunk<Activity[], { forceRefresh?: boolean; count?: number }, { rejectValue: string }>(
  'activities/fetchAllActivities',
  async ({ forceRefresh = false, count = 100 } = {}, { rejectWithValue }) => {
    try {
      console.log('[fetchAllActivities] Starter API-kall for å hente alle aktiviteter...');
      const response = await activitiesApi.getMoreActivities(forceRefresh, count, 0);
      console.log('[fetchAllActivities] Hentet response:', response?.length || 0, 'aktiviteter');
      return response;
    } catch (error) {
      console.error('[fetchAllActivities] Feil ved henting av alle aktiviteter:', error);
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
    setLoadedCount: (state, action: PayloadAction<number>) => {
      state.loadedCount = action.payload;
    },
    resetActivitiesState: (state) => {
      state.items = [];
      state.loadedCount = 0;
      state.totalCount = null;
      state.lastSync = null;
      state.error = null;
      state.status = 'idle';
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
        state.loadedCount = action.payload.length;
        state.lastSync = new Date().toISOString();
      })
      .addCase(fetchActivities.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload as string || 'Kunne ikke hente aktiviteter';
      })
      // fetchMoreActivities
      .addCase(fetchMoreActivities.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(fetchMoreActivities.fulfilled, (state, action: PayloadAction<Activity[]>) => {
        state.status = 'succeeded';
        // Legg til nye aktiviteter til eksisterende liste
        state.items = [...state.items, ...action.payload];
        state.loadedCount = state.items.length;
      })
      .addCase(fetchMoreActivities.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload as string || 'Kunne ikke hente flere aktiviteter';
      })
      // fetchActivityCount
      .addCase(fetchActivityCount.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(fetchActivityCount.fulfilled, (state, action: PayloadAction<number>) => {
        state.status = 'succeeded';
        state.totalCount = action.payload;
      })
      .addCase(fetchActivityCount.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload as string || 'Kunne ikke hente aktivitetsantall';
      })
      // fetchAllActivities
      .addCase(fetchAllActivities.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(fetchAllActivities.fulfilled, (state, action: PayloadAction<Activity[]>) => {
        state.status = 'succeeded';
        state.items = action.payload;
        state.loadedCount = action.payload.length;
        state.lastSync = new Date().toISOString();
      })
      .addCase(fetchAllActivities.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload as string || 'Kunne ikke hente alle aktiviteter';
      })
      // fetchActivitiesByDateRange
      .addCase(fetchActivitiesByDateRange.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(fetchActivitiesByDateRange.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.items = action.payload;
        state.loadedCount = action.payload.length;
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

export const { clearError, setLoadedCount, resetActivitiesState } = activitiesSlice.actions;

// Selectors
export const selectAllActivities = (state: { activities: ActivitiesState }) => state.activities.items;
export const selectActivitiesStatus = (state: { activities: ActivitiesState }) => state.activities.status;
export const selectActivitiesError = (state: { activities: ActivitiesState }) => state.activities.error;
export const selectActivitiesTotalCount = (state: { activities: ActivitiesState }) => state.activities.totalCount;
export const selectActivitiesLoadedCount = (state: { activities: ActivitiesState }) => state.activities.loadedCount;

export default activitiesSlice.reducer; 