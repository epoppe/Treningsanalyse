import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { sleepApi, errorHandler } from '../../utils/api';

// Definer typer
export interface SleepData {
  date: string;
  duration: number;  // Total søvnvarighet i timer
  deep_sleep: number;  // Dyp søvn i timer
  light_sleep: number;  // Lett søvn i timer
  rem_sleep: number;  // REM søvn i timer
  awake: number;  // Våken tid i timer
  start_time: string;  // Når man la seg
  end_time: string;  // Når man sto opp
}

interface SleepState {
  items: SleepData[];
  status: 'idle' | 'loading' | 'succeeded' | 'failed';
  error: string | null;
  lastSync: string | null;
}

// Initial state
const initialState: SleepState = {
  items: [],
  status: 'idle',
  error: null,
  lastSync: null
};

// Async thunks
export const fetchSleepByDateRange = createAsyncThunk(
  'sleep/fetchSleepByDateRange',
  async ({ startDate, endDate, forceRefresh = false }: { 
    startDate: string; 
    endDate: string; 
    forceRefresh?: boolean;
  }, { rejectWithValue }) => {
    try {
      const response = await sleepApi.getSleepByDateRange(startDate, endDate, forceRefresh);
      return response.sleep || [];
    } catch (error) {
      const errorInfo = errorHandler(error);
      return rejectWithValue(errorInfo.error);
    }
  }
);

// Slice
const sleepSlice = createSlice({
  name: 'sleep',
  initialState,
  reducers: {
    clearError: (state) => {
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchSleepByDateRange.pending, (state) => {
        state.status = 'loading';
        state.error = null;
      })
      .addCase(fetchSleepByDateRange.fulfilled, (state, action) => {
        state.status = 'succeeded';
        state.items = action.payload;
        state.lastSync = new Date().toISOString();
      })
      .addCase(fetchSleepByDateRange.rejected, (state, action) => {
        state.status = 'failed';
        state.error = action.payload as string || 'Kunne ikke hente søvndata for perioden';
      });
  },
});

export const { clearError } = sleepSlice.actions;
export default sleepSlice.reducer; 