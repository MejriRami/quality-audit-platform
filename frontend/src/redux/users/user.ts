import axiosInstance from "../../services/axiosInstance";
import type { AxiosError } from "axios";
import { logUserOut } from "../auth/auth";
import { getAuditorsFailure, getAuditorsRequest, getAuditorsSuccess } from "./user-slice";
import { GetAuditors } from "./user-types";

const parseAxiosError = (error: unknown) => {
  const err = error as AxiosError<unknown>;
  return {
    status: err.response?.status,
    data: err.response?.data,
  };
};

export const getAuditors: GetAuditors = async (dispatch) => {
  dispatch(getAuditorsRequest());
  const url = `/users/auditors`;

  try {
    const response = await axiosInstance.get(url);
    dispatch(getAuditorsSuccess(response.data));
    return true;
  } catch (error: unknown) {
    const { status } = parseAxiosError(error);
    dispatch(getAuditorsFailure());
    if (status === 401) {
      logUserOut(dispatch);
    }
  }

  return false;
};
