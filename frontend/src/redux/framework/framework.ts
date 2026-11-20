import axiosInstance from "../../services/axiosInstance";
import type { AxiosError } from "axios";
import { logUserOut } from "../auth/auth";
import { 
  getFrameworksRequest, getFrameworksSuccess, getFrameworksFailure,
  addFrameworkFailure, addFrameworkRequest, addFrameworkSuccess,
  deleteFrameworkFailure, deleteFrameworkRequest, deleteFrameworkSuccess,
  updateFrameworkFailure, updateFrameworkRequest, updateFrameworkSuccess
 } from "./framework-slice";
import { AddFramework, DeleteFramework, GetFrameworks, UpdateFramework } from "./framework-types";

const parseAxiosError = (error: unknown) => {
  const err = error as AxiosError<unknown>;
  return {
    status: err.response?.status,
    data: err.response?.data,
  };
};

export const getFrameworks: GetFrameworks = async (dispatch) => {
  dispatch(getFrameworksRequest());
  const url = `/framework/getAll`;

  try {
    const response = await axiosInstance.get(url);
    dispatch(getFrameworksSuccess(response.data));
    return true;
  } catch (error: unknown) {
    const { status } = parseAxiosError(error);
    dispatch(getFrameworksFailure());
    if (status === 401) {
      logUserOut(dispatch);
    }
  }

  return false;
};

export const addFramework: AddFramework = async (data, dispatch) => {
  dispatch(addFrameworkRequest());
  const url = `/framework/add`;

  try {
    const response = await axiosInstance.post(url, data);
    dispatch(addFrameworkSuccess(response.data));
    return true;
  } catch (error: unknown) {
    const { status } = parseAxiosError(error);
    dispatch(addFrameworkFailure());
    if (status === 401) {
      logUserOut(dispatch);
    }
  }

  return false;
};

export const deleteFramework: DeleteFramework = async (framework_id, dispatch) => {
  dispatch(deleteFrameworkRequest());
  const url = `/framework/${framework_id}`;

  try {
    const response = await axiosInstance.delete(url);
    dispatch(deleteFrameworkSuccess(response.data));
    return true;
  } catch (error: unknown) {
    const { status } = parseAxiosError(error);
    dispatch(deleteFrameworkFailure());
    if (status === 401) {
      logUserOut(dispatch);
    }
  }

  return false;
};

export const updateFramework: UpdateFramework = async (framework_id, data, dispatch) => {
  dispatch(updateFrameworkRequest());
  const url = `/framework/${framework_id}`;

  try {
    const response = await axiosInstance.put(url, data);
    dispatch(updateFrameworkSuccess(response.data));
    return true;
  } catch (error: unknown) {
    const { status } = parseAxiosError(error);
    dispatch(updateFrameworkFailure());
    if (status === 401) {
      logUserOut(dispatch);
    }
  }

  return false;
};
