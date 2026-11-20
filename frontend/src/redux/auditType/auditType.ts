import axiosInstance from "../../services/axiosInstance";
import type { AxiosError } from "axios";
import { logUserOut } from "../auth/auth";
import { 
  getAuditTypeFailure, getAuditTypeRequest, getAuditTypeSuccess,
  addAuditTypeFailure, addAuditTypeRequest, addAuditTypeSuccess,
  deleteAuditTypeFailure, deleteAuditTypeRequest, deleteAuditTypeSuccess
 } from "./auditType-slice";
import { AddAuditTypes, DeleteAuditTypes, GetAuditTypes } from "./auditType-types";

const parseAxiosError = (error: unknown) => {
  const err = error as AxiosError<unknown>;
  return {
    status: err.response?.status,
    data: err.response?.data,
  };
};

export const getAuditTypes: GetAuditTypes = async (dispatch) => {
  dispatch(getAuditTypeRequest());
  const url = `/audit-types/all`;

  try {
    const response = await axiosInstance.get(url);
    dispatch(getAuditTypeSuccess(response.data));
    return true;
  } catch (error: unknown) {
    const { status } = parseAxiosError(error);
    dispatch(getAuditTypeFailure());
    if (status === 401) {
      logUserOut(dispatch);
    }
  }

  return false;
};

export const addAuditTypes: AddAuditTypes = async (data, dispatch) => {
  dispatch(addAuditTypeRequest());
  const url = `/audit-types/add`;

  try {
    const response = await axiosInstance.post(url, data);
    dispatch(addAuditTypeSuccess(response.data));
    return true;
  } catch (error: unknown) {
    const { status } = parseAxiosError(error);
    dispatch(addAuditTypeFailure());
    if (status === 401) {
      logUserOut(dispatch);
    }
  }

  return false;
};

export const deleteAuditType: DeleteAuditTypes = async (audit_type_id, dispatch) => {
  dispatch(deleteAuditTypeRequest());
  const url = `/audit-types/${audit_type_id}`;

  try {
    const response = await axiosInstance.delete(url);
    dispatch(deleteAuditTypeSuccess(response.data));
    return true;
  } catch (error: unknown) {
    const { status } = parseAxiosError(error);
    dispatch(deleteAuditTypeFailure());
    if (status === 401) {
      logUserOut(dispatch);
    }
  }

  return false;
};
