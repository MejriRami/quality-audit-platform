import { Dispatch } from "@reduxjs/toolkit";
import axiosInstance from "../../services/axiosInstance";
import type { AxiosError } from "axios";
import { 
  loginFailure,
  loginRequest,
  loginSuccess,
  logout,
  resetPasswordFailure,
  resetPasswordRequest,
  resetPasswordSuccess,
  meFailure,
  meRequest,
  meSuccess
} from "./auth-slice";
import { Login, Me, ResetPassword } from "./auth-types";

const parseAxiosError = (error: unknown) => {
  const err = error as AxiosError<unknown>;
  return {
    status: err.response?.status,
    data: err.response?.data,
  };
};

export const login: Login = async (data, dispatch) => {
  dispatch(loginRequest());
  const url = `/login`;

  try {
    await localStorage.clear();
    const response = await axiosInstance.post(url, data);
    dispatch(loginSuccess(response.data));
    return true;
  } catch (error: unknown) {
    const { status, data } = parseAxiosError(error);
    dispatch(loginFailure(data));
    if (status === 401) {
      logUserOut(dispatch);
    }
  }

  return false;
};

export const logUserOut = (dispatch: Dispatch) => {
  dispatch(logout());
};

export const resetPassword: ResetPassword = async (data, dispatch) => {
  dispatch(resetPasswordRequest());
  const url = `/reset-password`;

  try {
    const response = await axiosInstance.post(url, data);
    dispatch(resetPasswordSuccess(response.data));
    return true;
  } catch (error: unknown) {
    const { status } = parseAxiosError(error);
    dispatch(resetPasswordFailure());
    if (status === 401) {
      logUserOut(dispatch);
    }
  }

  return false;
};

export const me: Me = async (dispatch) => {
  dispatch(meRequest());
  const url = `/me`;

  try {
      const response = await axiosInstance.get(url);
      dispatch(meSuccess(response.data));
      return true;
    } catch (error: unknown) {
      const { status } = parseAxiosError(error);
      dispatch(meFailure());
      if (status === 401) {
        logUserOut(dispatch);
      }
    }

  return false;
};


