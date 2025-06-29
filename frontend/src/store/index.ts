import { configureStore } from '@reduxjs/toolkit';
import activitiesReducer from './slices/activitiesSlice';

export const store = configureStore({
  reducer: {
    activities: activitiesReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch; 