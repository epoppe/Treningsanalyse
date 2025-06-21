import { configureStore } from '@reduxjs/toolkit';
import activitiesReducer from './slices/activitiesSlice';
import sleepReducer from './slices/sleepSlice';

export const store = configureStore({
  reducer: {
    activities: activitiesReducer,
    sleep: sleepReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch; 