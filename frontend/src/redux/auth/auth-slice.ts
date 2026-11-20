import { createSlice } from '@reduxjs/toolkit';
import { AuthState } from '../../redux/auth/auth-slice-types';

const storedRolesRaw = localStorage.getItem('roles');
const storedRoles = (() => {
  if (!storedRolesRaw) return [] as string[];
  try {
    const parsed = JSON.parse(storedRolesRaw);
    return Array.isArray(parsed) ? parsed.map((x) => String(x)) : [];
  } catch {
    return [];
  }
})();

const initialState: AuthState = {
  isAuthenticated: false,
  token: null,
  success: false,
  error: false,
  toast: '',
  role: storedRoles,
  user: null
};

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    loginRequest(state) {
      state.isAuthenticated = false;
      state.error = false;
      state.success = false;
      state.token = null;
    },
    loginSuccess(state, action) {
      console.log('Login Success Payload:', action.payload);
      state.isAuthenticated = true;
      state.toast='Successfully logged in';
      state.token = action.payload.access_token;
      state.role = Array.isArray(action.payload.roles) ? action.payload.roles : [];
      localStorage.setItem('token', action.payload.access_token);
      localStorage.setItem('roles', JSON.stringify(state.role));
      state.error = false;
      state.success = true;
    },
    loginFailure(state, action) {
      const detail = action.payload && typeof action.payload === 'object'
        ? (action.payload as { detail?: string }).detail
        : undefined;
      if (
         detail === 'User not found'
      ) {
        state.toast="User not found";
      } else if (
         detail === 'Invalid credentials'
      ) {
        state.toast="Invalid email or password";
      } else {
        state.toast = 'Login failed. Please try again.';
      }
      state.error = true
      state.success = false;
      state.isAuthenticated = false;
    },
    logout(state) {
      localStorage.removeItem('token');
      localStorage.removeItem('roles');
      state.isAuthenticated  = false;
      state.token = null;
      state.role = [];
    },
    resetAuthState(state) {
      state.error = false;
      state.success = false;
      state.toast = '';
    },
    setIsAuth(state) {
      state.isAuthenticated = true;
    },
    resetPasswordRequest(state) {
      state.error = false;
      state.success = false;
    },
    resetPasswordSuccess(state) {
      state.success = true;
      state.toast = 'Your password has been reset successfully';
      state.error = false;
    },
    resetPasswordFailure(state) {
      state.error = true;
      state.success = false;
      state.toast = 'Failed to reset password';
    },
    meRequest(state) {
      state.error = false;
      state.success = false;
      state.user = null;
    },
    meSuccess(state, action) {
      state.user = action.payload;
      state.success = true;
      state.error = false;
    },
    meFailure(state) {
      state.user = null;
      state.success = false;
      state.error = true;
    }
  }
});

export const {
  loginRequest,
  loginSuccess,
  loginFailure,
  logout,
  resetAuthState,
  setIsAuth,
  resetPasswordRequest,
  resetPasswordSuccess,
  resetPasswordFailure,
  meRequest,
  meSuccess,
  meFailure
} = authSlice.actions;

export default authSlice.reducer;
