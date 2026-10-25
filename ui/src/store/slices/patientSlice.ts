import { createSlice, PayloadAction } from '@reduxjs/toolkit';

interface PatientState {
  currentPatient: any | null;
  searchResults: any[];
  loading: boolean;
  error: string | null;
}

const initialState: PatientState = {
  currentPatient: null,
  searchResults: [],
  loading: false,
  error: null,
};

const patientSlice = createSlice({
  name: 'patient',
  initialState,
  reducers: {
    setCurrentPatient: (state, action: PayloadAction<any>) => {
      state.currentPatient = action.payload;
    },
    setSearchResults: (state, action: PayloadAction<any[]>) => {
      state.searchResults = action.payload;
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload;
    },
    setError: (state, action: PayloadAction<string>) => {
      state.error = action.payload;
    },
    clearError: (state) => {
      state.error = null;
    },
  },
});

export const {
  setCurrentPatient,
  setSearchResults,
  setLoading,
  setError,
  clearError,
} = patientSlice.actions;

export default patientSlice.reducer;